from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_from_directory, session
from functools import wraps
import sqlite3
import os
import re
from datetime import datetime, date, timedelta
import calendar
import json
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'finance_tracker_secret_2024')
DATABASE = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'finance_tracker.db'))
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads', 'statements')
ALLOWED_EXTENSIONS = {'pdf', 'csv', 'ofx', 'xlsx', 'xls'}
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS user_profile (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                dob TEXT,
                monthly_income REAL DEFAULT 0,
                other_income REAL DEFAULT 0,
                savings_goal_percent REAL DEFAULT 20,
                currency TEXT DEFAULT 'INR',
                demat_broker TEXT,
                demat_id TEXT,
                pan TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                icon TEXT DEFAULT '💰',
                color TEXT DEFAULT '#6c757d'
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                category_id INTEGER,
                description TEXT,
                date TEXT NOT NULL,
                payment_method TEXT DEFAULT 'upi',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            );

            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                due_day INTEGER NOT NULL,
                category TEXT,
                frequency TEXT DEFAULT 'monthly',
                is_paid INTEGER DEFAULT 0,
                last_paid TEXT,
                auto_debit INTEGER DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS investments (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                quantity REAL DEFAULT 0,
                buy_price REAL DEFAULT 0,
                current_price REAL DEFAULT 0,
                invested_amount REAL DEFAULT 0,
                current_value REAL DEFAULT 0,
                purchase_date TEXT,
                maturity_date TEXT,
                interest_rate REAL DEFAULT 0,
                symbol TEXT,
                folio_number TEXT,
                demat_account TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS savings_accounts (
                id INTEGER PRIMARY KEY,
                bank_name TEXT NOT NULL,
                account_type TEXT DEFAULT 'savings',
                account_number TEXT,
                balance REAL DEFAULT 0,
                interest_rate REAL DEFAULT 3.5,
                is_primary INTEGER DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS retirement_plan (
                id INTEGER PRIMARY KEY,
                current_age INTEGER DEFAULT 30,
                retirement_age INTEGER DEFAULT 60,
                life_expectancy INTEGER DEFAULT 80,
                current_monthly_expense REAL DEFAULT 0,
                inflation_rate REAL DEFAULT 6,
                expected_return_rate REAL DEFAULT 12,
                post_retirement_return REAL DEFAULT 7,
                current_corpus REAL DEFAULT 0,
                monthly_sip REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bank_statements (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                notes TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES savings_accounts(id) ON DELETE CASCADE
            );
        ''')

        # Add new columns to existing DBs (safe to run repeatedly)
        for col_sql in [
            "ALTER TABLE user_profile ADD COLUMN country TEXT DEFAULT 'India'",
            "ALTER TABLE user_profile ADD COLUMN govt_id_type TEXT DEFAULT 'PAN'",
            "ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN phone TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN dob TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN admin_id TEXT",
            "ALTER TABLE users ADD COLUMN security_question TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN security_answer_hash TEXT NOT NULL DEFAULT ''",
        ]:
            try:
                conn.execute(col_sql)
            except Exception:
                pass

        # Assign admin_id to default admin if missing
        admin = conn.execute("SELECT id, admin_id FROM users WHERE username='admin'").fetchone()
        if admin and not admin['admin_id']:
            conn.execute("UPDATE users SET admin_id='ADM001', role='admin' WHERE username='admin'")

        if conn.execute('SELECT COUNT(*) FROM categories').fetchone()[0] == 0:
            cats = [
                ('Salary', 'income', '💼', '#28a745'),
                ('Freelance', 'income', '💻', '#20c997'),
                ('Business', 'income', '🏢', '#17a2b8'),
                ('Investment Returns', 'income', '📈', '#ffc107'),
                ('Rental Income', 'income', '🏠', '#6f42c1'),
                ('Other Income', 'income', '💰', '#6c757d'),
                ('Food & Dining', 'expense', '🍔', '#dc3545'),
                ('Transportation', 'expense', '🚗', '#fd7e14'),
                ('Shopping', 'expense', '🛍️', '#e83e8c'),
                ('Entertainment', 'expense', '🎬', '#6f42c1'),
                ('Health & Medical', 'expense', '🏥', '#dc3545'),
                ('Education', 'expense', '📚', '#17a2b8'),
                ('Utilities', 'expense', '💡', '#ffc107'),
                ('Groceries', 'expense', '🛒', '#28a745'),
                ('Rent/EMI', 'expense', '🏠', '#6c757d'),
                ('Insurance', 'expense', '🛡️', '#17a2b8'),
                ('Travel', 'expense', '✈️', '#fd7e14'),
                ('Personal Care', 'expense', '💅', '#e83e8c'),
                ('Subscriptions', 'expense', '📱', '#6f42c1'),
                ('Investments/SIP', 'expense', '📊', '#20c997'),
                ('Other Expense', 'expense', '💸', '#6c757d'),
            ]
            conn.executemany('INSERT INTO categories (name, type, icon, color) VALUES (?, ?, ?, ?)', cats)

        if conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0:
            conn.execute(
                'INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)',
                ('admin', '', generate_password_hash('admin123'), 'admin')
            )
        conn.commit()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated


def fmt_inr(amount):
    try:
        amount = float(amount)
        if amount >= 10000000:
            return f"₹{amount/10000000:.2f}Cr"
        elif amount >= 100000:
            return f"₹{amount/100000:.2f}L"
        elif amount >= 1000:
            return f"₹{amount:,.0f}"
        return f"₹{amount:.2f}"
    except:
        return "₹0"


app.jinja_env.globals['fmt_inr'] = fmt_inr
app.jinja_env.globals['today'] = date.today().isoformat()


SECURITY_QUESTIONS = [
    "What was your childhood nickname?",
    "What is your mother's maiden name?",
    "What was the name of your first pet?",
    "What city were you born in?",
    "What was the name of your elementary school?",
    "What is your oldest sibling's middle name?",
    "What street did you grow up on?",
]


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username   = request.form.get('username', '').strip()
        email      = request.form.get('email', '').strip().lower()
        full_name  = request.form.get('full_name', '').strip()
        phone      = request.form.get('phone', '').strip()
        dob        = request.form.get('dob', '').strip()
        password   = request.form.get('password', '')
        confirm    = request.form.get('confirm_password', '')
        sec_q      = request.form.get('security_question', '').strip()
        sec_a      = request.form.get('security_answer', '').strip().lower()

        errors = []
        if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
            errors.append('Username must be 3–20 characters: letters, numbers, underscores only.')
        if not email or not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            errors.append('A valid email address is required.')
        if not full_name:
            errors.append('Full name is required.')
        if not phone or not re.match(r'^\+?[\d\s\-()]{7,20}$', phone):
            errors.append('A valid phone number is required.')
        if not dob:
            errors.append('Date of birth is required.')
        if len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')
        if not sec_q or not sec_a:
            errors.append('Security question and answer are required.')

        db = get_db()
        if not errors:
            if db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
                errors.append(f"Username '{username}' is already taken.")
            if db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone():
                errors.append(f"Email '{email}' is already registered.")

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('register.html', form=request.form,
                                   security_questions=SECURITY_QUESTIONS)

        db.execute(
            '''INSERT INTO users (username, email, password_hash, role, full_name, phone, dob,
               security_question, security_answer_hash) VALUES (?, ?, ?, 'user', ?, ?, ?, ?, ?)''',
            (username, email, generate_password_hash(password),
             full_name, phone, dob, sec_q, generate_password_hash(sec_a))
        )
        db.commit()
        flash('Account created! You can now sign in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form={}, security_questions=SECURITY_QUESTIONS)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'GET':
        # Fresh start unless continuing mid-flow
        if not request.args.get('continue'):
            for k in ('fp_step', 'fp_username', 'fp_question', 'fp_verified'):
                session.pop(k, None)
        step = session.get('fp_step', 1)
        return render_template('forgot_password.html', step=step,
                               question=session.get('fp_question', ''))

    step = session.get('fp_step', 1)

    if step == 1:
        identifier = request.form.get('username', '').strip()
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE username=? OR email=?', (identifier, identifier)
        ).fetchone()
        if not user or not user['security_question'] or not user['security_answer_hash']:
            flash('No account found, or no security question is set for that account.', 'danger')
            return render_template('forgot_password.html', step=1)
        session['fp_step'] = 2
        session['fp_username'] = user['username']
        session['fp_question'] = user['security_question']
        return render_template('forgot_password.html', step=2, question=user['security_question'])

    if step == 2:
        answer = request.form.get('security_answer', '').strip().lower()
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=?',
                          (session.get('fp_username'),)).fetchone()
        if not user or not check_password_hash(user['security_answer_hash'] or '', answer):
            flash('Incorrect answer. Please try again.', 'danger')
            return render_template('forgot_password.html', step=2,
                                   question=session.get('fp_question', ''))
        session['fp_step'] = 3
        session['fp_verified'] = True
        return render_template('forgot_password.html', step=3)

    if step == 3 and session.get('fp_verified'):
        new_pw  = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if len(new_pw) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('forgot_password.html', step=3)
        if new_pw != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('forgot_password.html', step=3)
        db = get_db()
        db.execute('UPDATE users SET password_hash=? WHERE username=?',
                   (generate_password_hash(new_pw), session['fp_username']))
        db.commit()
        for k in ('fp_step', 'fp_username', 'fp_question', 'fp_verified'):
            session.pop(k, None)
        flash('Password reset! You can now sign in.', 'success')
        return redirect(url_for('login'))

    return redirect(url_for('forgot_password'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if not user or not check_password_hash(user['password_hash'], password):
            flash('Invalid username or password.', 'danger')
            return render_template('login.html')
        if not user['is_active']:
            flash('This account has been deactivated. Contact an admin.', 'danger')
            return render_template('login.html')
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        next_url = request.form.get('next') or url_for('index')
        return redirect(next_url)
    return render_template('login.html', next=request.args.get('next', ''))


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been signed out.', 'info')
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    db = get_db()
    profile = db.execute('SELECT * FROM user_profile LIMIT 1').fetchone()
    if not profile:
        return redirect(url_for('setup'))
    return redirect(url_for('dashboard'))


@app.route('/setup', methods=['GET', 'POST'])
@login_required
def setup():
    if request.method == 'POST':
        db = get_db()
        db.execute('DELETE FROM user_profile')
        db.execute('''INSERT INTO user_profile
            (name, email, phone, dob, monthly_income, other_income, savings_goal_percent,
             demat_broker, demat_id, pan, country, govt_id_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (request.form['name'], request.form['email'], request.form['phone'],
             request.form['dob'], float(request.form.get('monthly_income', 0) or 0),
             float(request.form.get('other_income', 0) or 0),
             float(request.form.get('savings_goal_percent', 20) or 20),
             request.form.get('demat_broker', ''), request.form.get('demat_id', ''),
             request.form.get('pan', ''),
             request.form.get('country', 'India'),
             request.form.get('govt_id_type', 'PAN')))

        # Add primary savings account if provided
        if request.form.get('bank_name'):
            db.execute('''INSERT INTO savings_accounts (bank_name, account_type, account_number, balance, is_primary)
                VALUES (?, ?, ?, ?, 1)''',
                (request.form['bank_name'], request.form.get('account_type', 'savings'),
                 request.form.get('account_number', ''), float(request.form.get('bank_balance', 0) or 0)))

        # Retirement plan
        if request.form.get('current_age'):
            db.execute('DELETE FROM retirement_plan')
            db.execute('''INSERT INTO retirement_plan
                (current_age, retirement_age, life_expectancy, current_monthly_expense, current_corpus, monthly_sip)
                VALUES (?, ?, ?, ?, ?, ?)''',
                (int(request.form.get('current_age', 30)),
                 int(request.form.get('retirement_age', 60)),
                 int(request.form.get('life_expectancy', 80)),
                 float(request.form.get('monthly_expense', 0) or 0),
                 float(request.form.get('current_corpus', 0) or 0),
                 float(request.form.get('monthly_sip', 0) or 0)))
        db.commit()
        flash('Profile saved! Welcome to your Finance Dashboard.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('setup.html')


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    if request.method == 'POST':
        db.execute('''UPDATE user_profile SET name=?, email=?, phone=?, dob=?,
            monthly_income=?, other_income=?, savings_goal_percent=?,
            demat_broker=?, demat_id=?, pan=?, country=?, govt_id_type=? WHERE id=1''',
            (request.form['name'], request.form['email'], request.form['phone'],
             request.form['dob'], float(request.form.get('monthly_income', 0) or 0),
             float(request.form.get('other_income', 0) or 0),
             float(request.form.get('savings_goal_percent', 20) or 20),
             request.form.get('demat_broker', ''), request.form.get('demat_id', ''),
             request.form.get('pan', ''),
             request.form.get('country', 'India'),
             request.form.get('govt_id_type', 'PAN')))
        db.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('profile'))
    p = db.execute('SELECT * FROM user_profile LIMIT 1').fetchone()
    return render_template('profile.html', profile=p)


@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    profile = db.execute('SELECT * FROM user_profile LIMIT 1').fetchone()
    if not profile:
        return redirect(url_for('setup'))

    today = date.today()
    month_start = today.replace(day=1).isoformat()
    month_end = today.isoformat()

    # Monthly summary
    income = db.execute(
        "SELECT COALESCE(SUM(amount),0) as total FROM transactions WHERE type='income' AND date >= ? AND date <= ?",
        (month_start, month_end)).fetchone()['total']
    expense = db.execute(
        "SELECT COALESCE(SUM(amount),0) as total FROM transactions WHERE type='expense' AND date >= ? AND date <= ?",
        (month_start, month_end)).fetchone()['total']

    # Investments total
    investments = db.execute('SELECT * FROM investments').fetchall()
    total_invested = sum(i['invested_amount'] for i in investments)
    total_current = sum(i['current_value'] for i in investments)
    inv_gain = total_current - total_invested
    inv_gain_pct = (inv_gain / total_invested * 100) if total_invested > 0 else 0

    # Savings
    savings_accounts = db.execute('SELECT * FROM savings_accounts').fetchall()
    total_savings = sum(s['balance'] for s in savings_accounts)

    # Net worth
    net_worth = total_current + total_savings

    # Bills due this month
    bills = db.execute('SELECT * FROM bills WHERE is_paid=0 ORDER BY due_day').fetchall()
    bills_due = sum(b['amount'] for b in bills)

    # Recent transactions
    recent_txns = db.execute('''
        SELECT t.*, c.name as cat_name, c.icon, c.color FROM transactions t
        LEFT JOIN categories c ON t.category_id = c.id
        ORDER BY t.date DESC LIMIT 10''').fetchall()

    # Monthly spend by category
    cat_spend = [dict(r) for r in db.execute('''
        SELECT c.name, c.color, COALESCE(SUM(t.amount),0) as total
        FROM categories c
        LEFT JOIN transactions t ON t.category_id = c.id AND t.type='expense'
            AND t.date >= ? AND t.date <= ?
        WHERE c.type='expense'
        GROUP BY c.id ORDER BY total DESC LIMIT 8''',
        (month_start, month_end)).fetchall()]

    # 6-month trend
    trend_data = []
    for i in range(5, -1, -1):
        d = today.replace(day=1) - timedelta(days=1)
        for _ in range(i):
            d = d.replace(day=1) - timedelta(days=1)
        m_start = date(today.year if today.month - i > 0 else today.year - 1,
                       ((today.month - 1 - i) % 12) + 1, 1)
        last_day = calendar.monthrange(m_start.year, m_start.month)[1]
        m_end = m_start.replace(day=last_day)
        inc = db.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='income' AND date BETWEEN ? AND ?",
                         (m_start.isoformat(), m_end.isoformat())).fetchone()[0]
        exp = db.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='expense' AND date BETWEEN ? AND ?",
                         (m_start.isoformat(), m_end.isoformat())).fetchone()[0]
        trend_data.append({'month': m_start.strftime('%b %Y'), 'income': inc, 'expense': exp})

    return render_template('dashboard.html',
        profile=profile, income=income, expense=expense,
        total_invested=total_invested, total_current=total_current,
        inv_gain=inv_gain, inv_gain_pct=inv_gain_pct,
        total_savings=total_savings, net_worth=net_worth,
        bills=bills, bills_due=bills_due, recent_txns=recent_txns,
        cat_spend=cat_spend, trend_data=json.dumps(trend_data),
        savings_goal=profile['monthly_income'] * profile['savings_goal_percent'] / 100)


@app.route('/transactions', methods=['GET'])
@login_required
def transactions():
    db = get_db()
    profile = db.execute('SELECT * FROM user_profile LIMIT 1').fetchone()
    month = request.args.get('month', date.today().strftime('%Y-%m'))
    txn_type = request.args.get('type', 'all')
    cat_filter = request.args.get('category', '')

    year, mon = map(int, month.split('-'))
    last_day = calendar.monthrange(year, mon)[1]
    m_start = f"{month}-01"
    m_end = f"{month}-{last_day:02d}"

    query = '''SELECT t.*, c.name as cat_name, c.icon, c.color FROM transactions t
               LEFT JOIN categories c ON t.category_id = c.id
               WHERE t.date BETWEEN ? AND ?'''
    params = [m_start, m_end]

    if txn_type != 'all':
        query += ' AND t.type=?'
        params.append(txn_type)
    if cat_filter:
        query += ' AND t.category_id=?'
        params.append(cat_filter)

    query += ' ORDER BY t.date DESC'
    txns = db.execute(query, params).fetchall()
    categories = db.execute('SELECT * FROM categories ORDER BY type, name').fetchall()

    total_income = sum(t['amount'] for t in txns if t['type'] == 'income')
    total_expense = sum(t['amount'] for t in txns if t['type'] == 'expense')

    return render_template('transactions.html', txns=txns, categories=categories,
        month=month, txn_type=txn_type, cat_filter=cat_filter,
        total_income=total_income, total_expense=total_expense, profile=profile)


@app.route('/transactions/add', methods=['POST'])
@login_required
def add_transaction():
    db = get_db()
    db.execute('''INSERT INTO transactions (amount, type, category_id, description, date, payment_method, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (float(request.form['amount']), request.form['type'],
         request.form.get('category_id') or None,
         request.form.get('description', ''), request.form['date'],
         request.form.get('payment_method', 'upi'),
         request.form.get('notes', '')))
    db.commit()
    flash('Transaction added.', 'success')
    return redirect(url_for('transactions'))


@app.route('/transactions/<int:tid>/delete', methods=['POST'])
@login_required
def delete_transaction(tid):
    db = get_db()
    db.execute('DELETE FROM transactions WHERE id=?', (tid,))
    db.commit()
    flash('Transaction deleted.', 'info')
    return redirect(request.referrer or url_for('transactions'))


@app.route('/bills')
@login_required
def bills():
    db = get_db()
    profile = db.execute('SELECT * FROM user_profile LIMIT 1').fetchone()
    all_bills = db.execute('SELECT * FROM bills ORDER BY due_day').fetchall()
    today = date.today()
    total_monthly = sum(b['amount'] for b in all_bills if b['frequency'] == 'monthly')
    total_unpaid = sum(b['amount'] for b in all_bills if not b['is_paid'])
    return render_template('bills.html', bills=all_bills, today=today,
        total_monthly=total_monthly, total_unpaid=total_unpaid, profile=profile)


@app.route('/bills/add', methods=['POST'])
@login_required
def add_bill():
    db = get_db()
    db.execute('''INSERT INTO bills (name, amount, due_day, category, frequency, auto_debit, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (request.form['name'], float(request.form['amount']),
         int(request.form['due_day']), request.form.get('category', ''),
         request.form.get('frequency', 'monthly'),
         1 if request.form.get('auto_debit') else 0,
         request.form.get('notes', '')))
    db.commit()
    flash('Bill added.', 'success')
    return redirect(url_for('bills'))


@app.route('/bills/<int:bid>/paid', methods=['POST'])
@login_required
def mark_bill_paid(bid):
    db = get_db()
    db.execute("UPDATE bills SET is_paid=1, last_paid=? WHERE id=?",
               (date.today().isoformat(), bid))
    bill = db.execute('SELECT * FROM bills WHERE id=?', (bid,)).fetchone()
    # Add to transactions
    db.execute('''INSERT INTO transactions (amount, type, description, date, payment_method)
        VALUES (?, 'expense', ?, ?, 'auto_debit')''',
        (bill['amount'], f"Bill: {bill['name']}", date.today().isoformat()))
    db.commit()
    flash(f"Bill '{bill['name']}' marked as paid.", 'success')
    return redirect(url_for('bills'))


@app.route('/bills/<int:bid>/reset', methods=['POST'])
@login_required
def reset_bill(bid):
    db = get_db()
    db.execute("UPDATE bills SET is_paid=0 WHERE id=?", (bid,))
    db.commit()
    return redirect(url_for('bills'))


@app.route('/bills/<int:bid>/delete', methods=['POST'])
@login_required
def delete_bill(bid):
    db = get_db()
    db.execute('DELETE FROM bills WHERE id=?', (bid,))
    db.commit()
    flash('Bill deleted.', 'info')
    return redirect(url_for('bills'))


@app.route('/investments')
@login_required
def investments():
    db = get_db()
    profile = db.execute('SELECT * FROM user_profile LIMIT 1').fetchone()
    all_inv = db.execute('SELECT * FROM investments ORDER BY type, name').fetchall()

    by_type = {}
    for inv in all_inv:
        t = inv['type']
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(inv)

    total_invested = sum(i['invested_amount'] for i in all_inv)
    total_current = sum(i['current_value'] for i in all_inv)
    total_gain = total_current - total_invested
    gain_pct = (total_gain / total_invested * 100) if total_invested > 0 else 0

    type_labels = {'stock': 'Stocks (Demat)', 'mutual_fund': 'Mutual Funds',
                   'fd': 'Fixed Deposits', 'ppf': 'PPF', 'epf': 'EPF/PF',
                   'nps': 'NPS', 'gold': 'Gold', 'crypto': 'Crypto', 'other': 'Other'}

    return render_template('investments.html', investments=all_inv, by_type=by_type,
        total_invested=total_invested, total_current=total_current,
        total_gain=total_gain, gain_pct=gain_pct, type_labels=type_labels,
        profile=profile)


@app.route('/investments/add', methods=['POST'])
@login_required
def add_investment():
    db = get_db()
    invested = float(request.form.get('invested_amount', 0) or 0)
    qty = float(request.form.get('quantity', 0) or 0)
    buy_price = float(request.form.get('buy_price', 0) or 0)
    cur_price = float(request.form.get('current_price', 0) or buy_price)
    if qty and buy_price and not invested:
        invested = qty * buy_price
    cur_val = qty * cur_price if qty and cur_price else invested
    db.execute('''INSERT INTO investments
        (name, type, quantity, buy_price, current_price, invested_amount, current_value,
         purchase_date, maturity_date, interest_rate, symbol, folio_number, demat_account, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (request.form['name'], request.form['type'], qty, buy_price, cur_price,
         invested, cur_val,
         request.form.get('purchase_date', ''), request.form.get('maturity_date', ''),
         float(request.form.get('interest_rate', 0) or 0),
         request.form.get('symbol', ''), request.form.get('folio_number', ''),
         request.form.get('demat_account', ''), request.form.get('notes', '')))
    db.commit()
    flash('Investment added.', 'success')
    return redirect(url_for('investments'))


@app.route('/investments/<int:iid>/update', methods=['POST'])
@login_required
def update_investment(iid):
    db = get_db()
    inv = db.execute('SELECT * FROM investments WHERE id=?', (iid,)).fetchone()
    cur_price = float(request.form.get('current_price', inv['current_price']))
    qty = inv['quantity']
    cur_val = qty * cur_price if qty else float(request.form.get('current_value', inv['current_value']) or inv['current_value'])
    db.execute('UPDATE investments SET current_price=?, current_value=? WHERE id=?',
               (cur_price, cur_val, iid))
    db.commit()
    flash('Investment updated.', 'success')
    return redirect(url_for('investments'))


@app.route('/investments/<int:iid>/delete', methods=['POST'])
@login_required
def delete_investment(iid):
    db = get_db()
    db.execute('DELETE FROM investments WHERE id=?', (iid,))
    db.commit()
    flash('Investment removed.', 'info')
    return redirect(url_for('investments'))


@app.route('/savings')
@login_required
def savings():
    db = get_db()
    profile = db.execute('SELECT * FROM user_profile LIMIT 1').fetchone()
    accounts = db.execute('SELECT * FROM savings_accounts ORDER BY is_primary DESC, bank_name').fetchall()
    total = sum(a['balance'] for a in accounts)
    stmts_by_account = {}
    for s in db.execute('SELECT * FROM bank_statements ORDER BY uploaded_at DESC').fetchall():
        stmts_by_account.setdefault(s['account_id'], []).append(s)
    return render_template('savings.html', accounts=accounts, total=total, profile=profile,
                           stmts_by_account=stmts_by_account)


@app.route('/savings/add', methods=['POST'])
@login_required
def add_savings():
    db = get_db()
    if request.form.get('is_primary'):
        db.execute('UPDATE savings_accounts SET is_primary=0')
    db.execute('''INSERT INTO savings_accounts (bank_name, account_type, account_number, balance, interest_rate, is_primary, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (request.form['bank_name'], request.form.get('account_type', 'savings'),
         request.form.get('account_number', ''), float(request.form.get('balance', 0) or 0),
         float(request.form.get('interest_rate', 3.5) or 3.5),
         1 if request.form.get('is_primary') else 0,
         request.form.get('notes', '')))
    db.commit()
    flash('Account added.', 'success')
    return redirect(url_for('savings'))


@app.route('/savings/<int:sid>/update', methods=['POST'])
@login_required
def update_savings(sid):
    db = get_db()
    db.execute('UPDATE savings_accounts SET balance=? WHERE id=?',
               (float(request.form['balance']), sid))
    db.commit()
    flash('Balance updated.', 'success')
    return redirect(url_for('savings'))


@app.route('/savings/<int:sid>/delete', methods=['POST'])
@login_required
def delete_savings(sid):
    db = get_db()
    db.execute('DELETE FROM savings_accounts WHERE id=?', (sid,))
    db.execute('DELETE FROM bank_statements WHERE account_id=?', (sid,))
    db.commit()
    flash('Account removed.', 'info')
    return redirect(url_for('savings'))


@app.route('/savings/<int:sid>/upload-statement', methods=['POST'])
@login_required
def upload_statement(sid):
    db = get_db()
    if not db.execute('SELECT id FROM savings_accounts WHERE id=?', (sid,)).fetchone():
        flash('Account not found.', 'danger')
        return redirect(url_for('savings'))

    file = request.files.get('statement')
    if not file or file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('savings'))

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        flash('Invalid file type. Allowed: PDF, CSV, OFX, XLSX, XLS.', 'danger')
        return redirect(url_for('savings'))

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    safe_name = f"{sid}_{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
    dest = os.path.join(UPLOAD_FOLDER, safe_name)
    file.save(dest)

    db.execute(
        'INSERT INTO bank_statements (account_id, filename, original_name, file_size, notes) VALUES (?, ?, ?, ?, ?)',
        (sid, safe_name, file.filename, os.path.getsize(dest), request.form.get('notes', ''))
    )
    db.commit()
    flash('Statement uploaded.', 'success')
    return redirect(url_for('savings'))


@app.route('/savings/statements/<int:stmt_id>/download')
@login_required
def download_statement(stmt_id):
    db = get_db()
    stmt = db.execute('SELECT * FROM bank_statements WHERE id=?', (stmt_id,)).fetchone()
    if not stmt:
        flash('Statement not found.', 'danger')
        return redirect(url_for('savings'))
    return send_from_directory(UPLOAD_FOLDER, stmt['filename'],
                               as_attachment=True, download_name=stmt['original_name'])


@app.route('/savings/statements/<int:stmt_id>/delete', methods=['POST'])
@login_required
def delete_statement(stmt_id):
    db = get_db()
    stmt = db.execute('SELECT * FROM bank_statements WHERE id=?', (stmt_id,)).fetchone()
    if stmt:
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, stmt['filename']))
        except FileNotFoundError:
            pass
        db.execute('DELETE FROM bank_statements WHERE id=?', (stmt_id,))
        db.commit()
        flash('Statement removed.', 'info')
    return redirect(url_for('savings'))


@app.route('/retirement', methods=['GET', 'POST'])
@login_required
def retirement():
    db = get_db()
    profile = db.execute('SELECT * FROM user_profile LIMIT 1').fetchone()
    plan = db.execute('SELECT * FROM retirement_plan LIMIT 1').fetchone()

    if request.method == 'POST':
        current_age = int(request.form.get('current_age', 30))
        retirement_age = int(request.form.get('retirement_age', 60))
        life_expectancy = int(request.form.get('life_expectancy', 80))
        monthly_expense = float(request.form.get('current_monthly_expense', 0) or 0)
        inflation = float(request.form.get('inflation_rate', 6) or 6)
        return_rate = float(request.form.get('expected_return_rate', 12) or 12)
        post_ret_return = float(request.form.get('post_retirement_return', 7) or 7)
        current_corpus = float(request.form.get('current_corpus', 0) or 0)
        monthly_sip = float(request.form.get('monthly_sip', 0) or 0)

        if plan:
            db.execute('''UPDATE retirement_plan SET current_age=?, retirement_age=?, life_expectancy=?,
                current_monthly_expense=?, inflation_rate=?, expected_return_rate=?,
                post_retirement_return=?, current_corpus=?, monthly_sip=? WHERE id=1''',
                (current_age, retirement_age, life_expectancy, monthly_expense, inflation,
                 return_rate, post_ret_return, current_corpus, monthly_sip))
        else:
            db.execute('''INSERT INTO retirement_plan
                (current_age, retirement_age, life_expectancy, current_monthly_expense,
                 inflation_rate, expected_return_rate, post_retirement_return, current_corpus, monthly_sip)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (current_age, retirement_age, life_expectancy, monthly_expense, inflation,
                 return_rate, post_ret_return, current_corpus, monthly_sip))
        db.commit()
        plan = db.execute('SELECT * FROM retirement_plan LIMIT 1').fetchone()
        flash('Retirement plan updated.', 'success')

    result = None
    if plan:
        yrs_to_retire = plan['retirement_age'] - plan['current_age']
        ret_duration = plan['life_expectancy'] - plan['retirement_age']
        r_monthly = plan['expected_return_rate'] / 100 / 12
        inflation_m = plan['inflation_rate'] / 100 / 12
        post_r_monthly = plan['post_retirement_return'] / 100 / 12

        # Future monthly expense at retirement
        future_monthly_exp = plan['current_monthly_expense'] * ((1 + plan['inflation_rate'] / 100) ** yrs_to_retire)

        # Corpus needed at retirement (PV of annuity)
        n_months_ret = ret_duration * 12
        if post_r_monthly > inflation_m:
            real_rate = (1 + post_r_monthly) / (1 + inflation_m) - 1
            corpus_needed = future_monthly_exp * (1 - (1 + real_rate) ** (-n_months_ret)) / real_rate
        else:
            corpus_needed = future_monthly_exp * n_months_ret

        # Current corpus future value
        n_months_inv = yrs_to_retire * 12
        corpus_fv = plan['current_corpus'] * ((1 + r_monthly) ** n_months_inv)

        # SIP future value
        if r_monthly > 0:
            sip_fv = plan['monthly_sip'] * (((1 + r_monthly) ** n_months_inv - 1) / r_monthly) * (1 + r_monthly)
        else:
            sip_fv = plan['monthly_sip'] * n_months_inv

        projected_corpus = corpus_fv + sip_fv
        shortfall = max(0, corpus_needed - projected_corpus)
        surplus = max(0, projected_corpus - corpus_needed)

        # Required monthly SIP
        if r_monthly > 0 and n_months_inv > 0:
            req_sip = max(0, (corpus_needed - corpus_fv) * r_monthly /
                         (((1 + r_monthly) ** n_months_inv - 1) * (1 + r_monthly)))
        else:
            req_sip = max(0, (corpus_needed - corpus_fv) / n_months_inv) if n_months_inv else 0

        result = {
            'yrs_to_retire': yrs_to_retire,
            'ret_duration': ret_duration,
            'future_monthly_exp': future_monthly_exp,
            'corpus_needed': corpus_needed,
            'corpus_fv': corpus_fv,
            'sip_fv': sip_fv,
            'projected_corpus': projected_corpus,
            'shortfall': shortfall,
            'surplus': surplus,
            'req_sip': req_sip,
            'on_track': projected_corpus >= corpus_needed
        }

    return render_template('retirement.html', plan=plan, result=result, profile=profile)


@app.route('/reports')
@login_required
def reports():
    db = get_db()
    profile = db.execute('SELECT * FROM user_profile LIMIT 1').fetchone()

    # Annual summary - current year
    year = date.today().year
    monthly_data = []
    for m in range(1, 13):
        last_day = calendar.monthrange(year, m)[1]
        m_start = f"{year}-{m:02d}-01"
        m_end = f"{year}-{m:02d}-{last_day:02d}"
        inc = db.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='income' AND date BETWEEN ? AND ?",
                         (m_start, m_end)).fetchone()[0]
        exp = db.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='expense' AND date BETWEEN ? AND ?",
                         (m_start, m_end)).fetchone()[0]
        monthly_data.append({'month': calendar.month_abbr[m], 'income': inc, 'expense': exp, 'saving': inc - exp})

    # Category breakdown for year
    cat_data = [dict(r) for r in db.execute('''
        SELECT c.name, c.color, COALESCE(SUM(t.amount),0) as total
        FROM categories c
        LEFT JOIN transactions t ON t.category_id = c.id AND t.type='expense'
            AND strftime('%Y', t.date) = ?
        WHERE c.type='expense'
        GROUP BY c.id HAVING total > 0 ORDER BY total DESC''',
        (str(year),)).fetchall()]

    # Investment allocation
    inv_alloc = [dict(r) for r in db.execute('''
        SELECT type, COALESCE(SUM(current_value),0) as total
        FROM investments GROUP BY type HAVING total > 0''').fetchall()]

    # Annual totals
    ann_income = sum(m['income'] for m in monthly_data)
    ann_expense = sum(m['expense'] for m in monthly_data)
    ann_saving = ann_income - ann_expense

    return render_template('reports.html',
        monthly_data=json.dumps(monthly_data), cat_data=cat_data,
        inv_alloc=inv_alloc, ann_income=ann_income,
        ann_expense=ann_expense, ann_saving=ann_saving,
        year=year, profile=profile)


@app.route('/admin')
@login_required
def admin():
    db = get_db()
    profile = db.execute('SELECT * FROM user_profile LIMIT 1').fetchone()
    users = db.execute('SELECT * FROM users ORDER BY role DESC, username').fetchall()
    return render_template('admin.html', users=users, profile=profile,
                           security_questions=SECURITY_QUESTIONS)


@app.route('/admin/add-user', methods=['POST'])
@login_required
def admin_add_user():
    username  = request.form.get('username', '').strip()
    email     = request.form.get('email', '').strip().lower()
    full_name = request.form.get('full_name', '').strip()
    phone     = request.form.get('phone', '').strip()
    dob       = request.form.get('dob', '').strip()
    password  = request.form.get('password', '')
    role      = request.form.get('role', 'user')

    if not username or not password:
        flash('Username and password are required.', 'danger')
        return redirect(url_for('admin'))
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        flash('Username must be 3–20 chars: letters, numbers, underscores.', 'danger')
        return redirect(url_for('admin'))
    if len(password) < 8:
        flash('Password must be at least 8 characters.', 'danger')
        return redirect(url_for('admin'))

    db = get_db()
    if db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
        flash(f"Username '{username}' already exists.", 'danger')
        return redirect(url_for('admin'))
    if email and db.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone():
        flash(f"Email '{email}' is already registered.", 'danger')
        return redirect(url_for('admin'))

    admin_id = None
    if role == 'admin':
        count = db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
        admin_id = f"ADM{(count + 1):03d}"

    db.execute(
        '''INSERT INTO users (username, email, password_hash, role, full_name, phone, dob, admin_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (username, email, generate_password_hash(password), role,
         full_name, phone, dob, admin_id)
    )
    db.commit()
    flash(f"User '{username}' created{' (Admin ID: ' + admin_id + ')' if admin_id else ''}.", 'success')
    return redirect(url_for('admin'))


@app.route('/admin/users/<int:uid>/delete', methods=['POST'])
@login_required
def admin_delete_user(uid):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin'))
    if user['role'] == 'admin' and db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] == 1:
        flash('Cannot delete the last admin account.', 'danger')
        return redirect(url_for('admin'))
    db.execute('DELETE FROM users WHERE id=?', (uid,))
    db.commit()
    flash(f"User '{user['username']}' deleted.", 'info')
    return redirect(url_for('admin'))


@app.route('/admin/users/<int:uid>/toggle', methods=['POST'])
@login_required
def admin_toggle_user(uid):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin'))
    new_state = 0 if user['is_active'] else 1
    db.execute('UPDATE users SET is_active=? WHERE id=?', (new_state, uid))
    db.commit()
    state_label = 'activated' if new_state else 'deactivated'
    flash(f"User '{user['username']}' {state_label}.", 'success')
    return redirect(url_for('admin'))


@app.route('/admin/users/<int:uid>/reset-password', methods=['POST'])
@login_required
def admin_reset_password(uid):
    new_password = request.form.get('new_password', '')
    if not new_password:
        flash('New password cannot be empty.', 'danger')
        return redirect(url_for('admin'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin'))
    db.execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(new_password), uid))
    db.commit()
    flash(f"Password reset for '{user['username']}'.", 'success')
    return redirect(url_for('admin'))


init_db()

if __name__ == '__main__':
    print("\n" + "="*50)
    print("  Finance Tracker is running!")
    print("  Open: http://127.0.0.1:5000")
    print("="*50 + "\n")
    app.run(debug=True, host='127.0.0.1', port=5000)
