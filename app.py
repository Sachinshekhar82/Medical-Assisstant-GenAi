import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from googletrans import Translator
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
import google.generativeai as genai

load_dotenv(find_dotenv())

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or 'change-this-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

translator = Translator()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("Missing GOOGLE_API_KEY in .env")
genai.configure(api_key=api_key)
MODEL_NAME = 'models/gemini-2.5-pro'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))


class QueryHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    question = db.Column(db.Text)
    answer = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def get_gemini_response(prompt):
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(prompt)
    return response.text


@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    response = None
    user_input = ""
    selected_lang = request.form.get('language', 'en')
    if request.method == 'POST':
        user_input = request.form.get('user_input', '').strip()
        if not user_input:
            flash('Please enter a medical query.', 'warning')
        else:
            # Translate user input to English if needed
            if selected_lang != 'en':
                user_input_en = translator.translate(user_input, dest='en').text
            else:
                user_input_en = user_input

            prompt = f"""Imagine you are a medical expert and you are giving accurate medical advice to a patient. 
You are presented with a medical query and asked to provide a response with a detailed explanation. 
Note that dont mention any inaccurate or misleading information.

Medical Query: {user_input_en}

Key Details:
- Provide precise information related to the patient's medical concern.
- Indicate if any diagnostic tests or examinations have been performed.
- Specify the current medications or treatments prescribed.
- The response should be in a paragraph format but not in point-wise.
- If only a specific disease name is mentioned, response must contain the symptoms, causes, and treatment of the disease with respective headings.

Guidelines:
- Use clear and concise language.
- The vocabulary should be appropriate for the medical context.
- Include specific parameters or considerations within the medical context.
- If the response contains a list of items, convert it into a paragraph format.
- Avoid using abbreviations or acronyms.
- Avoid Headings and Subheadings; just give the complete response in a paragraph format.
- Refrain from presenting inaccurate or ambiguous information.
- Ensure the query is focused and not overly broad."""

            gemini_response_en = get_gemini_response(prompt)

            # Translate response to selected language if needed
            if selected_lang != 'en':
                response = translator.translate(gemini_response_en, dest=selected_lang).text
            else:
                response = gemini_response_en

            # Store in history
            history = QueryHistory(user_id=current_user.id, question=user_input, answer=response)
            db.session.add(history)
            db.session.commit()

    return render_template('index.html', user_input=user_input, response=response, selected_lang=selected_lang)


@app.route('/history')
@login_required
def history():
    user_history = QueryHistory.query.filter_by(user_id=current_user.id).order_by(QueryHistory.timestamp.desc()).all()
    return render_template('history.html', history=user_history)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            flash("Logged in successfully!", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid username or password", "danger")
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash("Username already exists", "warning")
        else:
            new_user = User(username=username, password=password)
            db.session.add(new_user)
            db.session.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

