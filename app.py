from flask import Flask, render_template, request, url_for, session, redirect
import psycopg2
from dotenv import load_dotenv # Remove this line if needed, this is for practice hide database passwords
import os # Remove this line if needed as well, this is just for the passwords
from scrapers import get_gas_prices
from functools import wraps

app = Flask(__name__)

load_dotenv() # Remove this line if needed

app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")
psql_password = os.getenv("PSQL_PASSWORD") # Remove this line if need

conn = psycopg2.connect(database="rapid_db", user="postgres",
password=psql_password, host="localhost", port="5432")  # Replace psql_password with the password for your psql user

cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS incidents (
        incident_id SERIAL PRIMARY KEY,
        userid INT NOT NULL REFERENCES users(userid),
        county VARCHAR(30) NOT NULL,
        address VARCHAR(120) NOT NULL,
        occurrence VARCHAR(10) NOT NULL,
        description TEXT NOT NULL,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status VARCHAR(20) DEFAULT 'Under Review'
    );
""")
# ensure userid column exists in incidents
cur.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'incidents'
              AND column_name = 'userid'
        ) THEN
            ALTER TABLE incidents ADD COLUMN userid INT REFERENCES users(userid);
        END IF;
    END
    $$;
""")

# add date column if it doesn't already exist in incidents
cur.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name='incidents' AND column_name='date'
        ) THEN
            ALTER TABLE incidents ADD COLUMN date TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        END IF;
    END
    $$;
""")

# status column for incidents table
cur.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name='incidents' AND column_name='status'
        ) THEN
            ALTER TABLE incidents ADD COLUMN status VARCHAR(20) DEFAULT 'Under Review';
        END IF;
    END
    $$;
""")

# create users table if it doesnt already exist
# for storing account credentials and role info
cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    userid SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(300) NOT NULL,
    role VARCHAR(20) DEFAULT 'user'
);
""")

conn.commit()
cur.close()
conn.close()

# added decorator for updating routes w/ admin access 
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('index'))
        if session.get('role') != 'admin':
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# added decorator for updating header routes w/ admin access
@app.context_processor
def inject_user():
    return dict(username=session.get('username'))


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if session.get('role') == 'admin':
        return redirect(url_for('all_submitted_reports'))
    
    userid = session.get('user_id')

    if request.method == 'POST':
        county = request.form.get('county')
        address = request.form['address']
        occurrence = request.form['occurrence']
        description = request.form['description']
        

        conn = psycopg2.connect(database="rapid_db", user="postgres",
                                password=psql_password, host="localhost")
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO incidents (userid, county, address, occurrence, description)
            VALUES (%s, %s, %s, %s, %s);
        ''', (userid, county, address, occurrence, description))  

        conn.commit()
        cur.close()
        conn.close()

    conn = psycopg2.connect(database="rapid_db", user="postgres",
                            password=psql_password, host="localhost")
    cur = conn.cursor()
    cur.execute("SELECT * FROM incidents WHERE userid = %s ORDER BY date DESC;", (userid,))
    incidents = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('dashboard.html', username=session.get('username'), incidents=incidents)

@app.route('/resources')
def resources():
    if session.get('role') == 'admin':
        return redirect(url_for('all_submitted_reports'))
    return render_template('resources.html')

@app.route('/submit_resources', methods=['POST'])
def submit_resources():
    flat_cost = 0
    man_hour_cost = 0
    gas_price, diesel_price = get_gas_prices()
    prices = {
        'sandbags': 2.5,
        'helicopters': 3000,
        'gasoline': gas_price,
        'diesel': diesel_price,
    }
    for item, price in prices.items():
        quantity = request.form.get(item)
        if quantity and quantity.isdigit():
            flat_cost += int(quantity) * price
    responders = {
        'medical_responders': 50,
        'police_responders': 45,
        'fire_responders': 55
    }
    for role, hourly_rate in responders.items():
        num = request.form.get(role)
        if num and num.isdigit():
            man_hour_cost += int(num) * hourly_rate
    message = f"Your estimated request costs ${flat_cost:.2f} flat, ${man_hour_cost:.2f} per first responder man-hour. Additionally, helicopters cost $600 per hour of flight. Custom resources are not included in this estimate."
    return render_template('summary.html', message=message)


@app.route('/submitted_reports')
def submitted_reports():
    user_id = session.get('user_id')
    conn = psycopg2.connect(database="rapid_db", user="postgres",
                            password=psql_password, host="localhost")
    cur = conn.cursor()
    cur.execute("SELECT * FROM incidents WHERE userid = %s ORDER BY date DESC;", (user_id,))
    incidents = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('submitted_reports.html', incidents=incidents)


@app.route('/admin/demographics')
def demographics():
    return render_template('admin/demographics.html')


@app.route('/admin/city_reports')
@admin_required
def city_reports():
    return render_template('admin/city_reports.html')


@app.route('/admin/county_reports')
@admin_required
def county_reports():
    return render_template('admin/county_reports.html')


@app.route("/admin/anticipated_costs")
@admin_required
def anticipated_costs():
    return render_template("admin/anticipated_costs.html")


@app.route("/admin/mock-approval")
@admin_required
def mock_approval():
    return render_template("admin/mock_approval.html")

from werkzeug.security import generate_password_hash

@app.route('/create_account', methods=['GET', 'POST'])
def create_account():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        hashed_password = generate_password_hash(password)

        conn = psycopg2.connect(database="rapid_db", user="postgres",
            password=psql_password, host="localhost", port="5432")
        cur = conn.cursor()

        cur.execute("SELECT username FROM users WHERE username = %s", (username,))
        existing_user = cur.fetchone()

        if existing_user:
            cur.close()
            conn.close()
            error = "Username already exists. Please choose another one."
            return render_template('create_account.html', error=error)
        
        # insert new user here if username is unique
        cur.execute(
            '''INSERT INTO users (username, email, password)
            VALUES (%s, %s, %s);''',
            (username, email, hashed_password)
        )

        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('index')) 
    return render_template('create_account.html')

from werkzeug.security import check_password_hash

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = psycopg2.connect(database="rapid_db", user="postgres",
            password=psql_password, host="localhost", port="5432")
        cur = conn.cursor()
        cur.execute("SELECT userid, password, role FROM users WHERE username = %s", (username,))
        result = cur.fetchone()
        print("Fetched from DB:", result)#debug
        print("Password entered:", password)#debug
        if result: #debug
            print("Hash from DB:", result[0])
            print("Check passed:", check_password_hash(result[1], password))
        cur.close()
        conn.close()

        if result and check_password_hash(result[1], password):
            session['user_id'] = result[0]
            session['role'] = result[2]
            session['username'] = username

            if result[2] == 'admin':  # result[2] is the role
                return redirect(url_for('all_submitted_reports'))
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid username or password"

    return render_template('index.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin/all_submitted_reports')
@admin_required
def all_submitted_reports():
    conn = psycopg2.connect(database="rapid_db", user="postgres",
                            password=psql_password, host="localhost")
    cur = conn.cursor()
    cur.execute("SELECT * FROM incidents ORDER BY date DESC;")
    incidents = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
    'admin/all_submitted_reports.html',
    incidents=incidents,
    username=session.get('username')
)


if __name__ == '__main__':
   app.run(debug = True)
