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

# Just create a function that would connect to the postgres application

cur = conn.cursor()

# Create a function that gets the user's specified role in postgres, so get the role that is not the username
def get_user_role(username, conn):
    cur = conn.cursor()
    try:
        cur.execute(
            '''
            SELECT rolname FROM pg_roles
            WHERE oid IN (
                SELECT roleid
                FROM pg_auth_members
                WHERE member = (
                    SELECT oid FROM pg_roles WHERE rolname = %s
                )
            )
            AND rolname IN ('community_member', 'city_manager', 'state_official', 'admin')
            ''', (username, )
        )

        roles = cur.fetchall()

        # Debugging
        print(f"Roles for user {username}: {roles}")
        
        # Turn the roles into a list
        role_names = [role[0] for role in roles]
        
        # Order eveerything by roles
        if 'admin' in role_names:
            return 'admin'
        elif 'state_official' in role_names:
            return 'state_official'
        elif 'city_manager' in role_names:
            return 'city_manager'
        elif 'community_member' in role_names:
            return 'community_member'
        else:
            return 'user'
    finally:
        cur.close()

# We need to create the roles for the users in the database, community members, city managers, and state/federal officials
cur.execute(
    '''
    DO
    $do$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'community_member') THEN
            CREATE ROLE community_member;
        END IF;
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'city_manager') THEN
            CREATE ROLE city_manager;
        END IF;
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'state_official') THEN
            CREATE ROLE state_official;
        END IF;
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'admin') THEN
            CREATE ROLE admin;
        END IF;
    END
    $do$;
    '''
)


# create incidents table if it doesn't exist
# this is storing all incident report data submitted by users
cur.execute(
    '''CREATE TABLE IF NOT EXISTS incidents( \
        county VARCHAR(30), address VARCHAR(120),\
        occurrence VARCHAR(10), description TEXT);'''
)

# resource request table will be created if the table does not already exist
# This is just a sample code for the resource request table, please modify it to your needs
cur.execute(
    '''CREATE TABLE IF NOT EXISTS resource_req( \
        id SERIAL PRIMARY KEY, \
        resource_type VARCHAR(50), \
        description TEXT, \
        status VARCHAR(20) DEFAULT 'pending', \
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP \
    );'''
)

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

# create users table if it doesnt already exist
# for storing account credentials and role info
cur.execute(
    '''CREATE TABLE IF NOT EXISTS users(
        username VARCHAR(50) PRIMARY KEY,
        email VARCHAR(100),
        password VARCHAR(300),
        role VARCHAR(20) DEFAULT 'user');'''
)

# Now we can grant the permissions to the roles
cur.execute(
    '''
    GRANT SELECT, INSERT ON TABLE incidents TO community_member;
    GRANT SELECT, UPDATE, DELETE ON TABLE incidents TO city_manager;
    GRANT SELECT, INSERT ON TABLE resource_req TO city_manager;
    GRANT SELECT, UPDATE ON TABLE incidents TO state_official;
    GRANT SELECT, UPDATE, DELETE ON TABLE resource_req TO state_official;
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO admin;
    '''
)

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

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        county = request.form.get('county')
        address = request.form['address']
        occurrence = request.form['occurrence']
        description = request.form['description']

        conn = psycopg2.connect(database="rapid_db", user="postgres",
                                password=psql_password, host="localhost")
        cur = conn.cursor()

        cur.execute(
    '''INSERT INTO incidents (county, address, occurrence, description)
       VALUES (%s, %s, %s, %s);''',
    (county, address, occurrence, description)
    )   

        conn.commit()
        cur.close()
        conn.close()

    conn = psycopg2.connect(database="rapid_db", user="postgres",
                            password=psql_password, host="localhost")
    cur = conn.cursor()
    cur.execute("SELECT * FROM incidents ORDER BY date DESC;")
    incidents = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('dashboard.html', username=session.get('username'), incidents=incidents)

@app.route('/resources')
def resources():
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
    conn = psycopg2.connect(database="rapid_db", user="postgres",
                            password=psql_password, host="localhost")
    cur = conn.cursor()
    cur.execute("SELECT * FROM incidents ORDER BY date DESC;")
    incidents = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('submitted_reports.html', incidents=incidents)


@app.route('/demographics')
def demographics():
    return render_template('demographics.html')


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
        username = request.form['username'] # Lets have a psql role and a flask role, so flask is the app based logic
        email = request.form['email']
        password = request.form['password']

        hashed_password = generate_password_hash(password)

        conn = psycopg2.connect(database="rapid_db", user="postgres",
            password=psql_password, host="localhost", port="5432")
        cur = conn.cursor()

        # Check if the username already exists in the database
        try:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (username,))
            existing_role = cur.fetchone()
            
            if not existing_role: # If the user does not exist, create user for the database
                if not username.isalnum(): # This meant to be safe for SQL to inject the username into SQL
                    raise ValueError("Username must contain only alphanumeric characters")

                # Use string formatting for creating user and granting roles to the specific user
                cur.execute(f"CREATE USER \"{username}\" WITH PASSWORD %s;", (password,))
                cur.execute(f"GRANT community_member TO \"{username}\";")
        except Exception as e:
            error = f"User creation failed: {e}"

        # This part of the code create the user for postgres and automatically assigns the community member role for the user
        # Postgres automatically hashes the plaintext password

        # cur.execute("SELECT username FROM users WHERE username = %s", (username,)) # May not need this line, we can check if the user exists through postgresql commands

        # existing_user = cur.fetchone()

        '''
        if existing_user:
            cur.close()
            conn.close()
            error = "Username already exists. Please choose another one."
            return render_template('create_account.html', error=error)
        '''
        
        # insert new user here if username is unique
        # We really only need the username and emails here, the password is stored safely in postgres
        # We do not need the email
        cur.execute(
            '''INSERT INTO users (username, email, password)
            VALUES (%s, %s, %s)
            ON CONFLICT (username) DO NOTHING;''',
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

        # If the user exists within the postgres authentication
        conn = psycopg2.connect(database="rapid_db", user="postgres", # Change this to the specific user logging in the database
            password=psql_password, host="localhost", port="5432")

        cur = conn.cursor()

        # This checks from the database selection if the user already exists for the database
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (username,)) # Checks the users that are in the roles list in psql
        existing_user = cur.fetchone()

        if existing_user:
            # If the user is able to login into the database, the database will have specific permissions
            # By the user
            try:
                conn =  psycopg2.connect(database="rapid_db", user=username, # Now the specific user is logging into the database, no need to manually hash password
                password=password, host="localhost", port="5432")
                session['username'] = username
                session['role'] = get_user_role(username, conn) # Get the role of the user from the database, maybe this could work?
                return redirect(url_for('dashboard'))
            except OperationalError as e:
                error = "Invalid username or password"
        else:
            error = "User does not exist"

        # May not need this chunk of code
        '''
        cur.execute("SELECT password, role FROM users WHERE username = %s", (username,))
        result = cur.fetchone()
        print("Fetched from DB:", result)#debug
        print("Password entered:", password)#debug
        if result: #debug
            print("Hash from DB:", result[0])
            print("Check passed:", check_password_hash(result[0], password))
        cur.close()
        conn.close()
        '''

        # Might not need this code
        '''
        if result and check_password_hash(result[0], password):
            session['username'] = username
            session['role'] = result[1]
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid username or password"
        '''

    return render_template('index.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
   app.run(debug = True)
