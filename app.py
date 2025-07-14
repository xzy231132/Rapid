from flask import Flask, render_template, request, url_for
import psycopg2
from dotenv import load_dotenv # Remove this line if needed, this is for practice hide database passwords
import os # Remove this line if needed as well, this is just for the passwords


app = Flask(__name__)

load_dotenv() # Remove this line if needed

psql_password = os.getenv("PSQL_PASSWORD") # Remove this line if need

conn = psycopg2.connect(database="rapid_db", user="postgres",
password=psql_password, host="localhost")  # Replace psql_password with the password for your psql user

cur = conn.cursor()

cur.execute(
    '''CREATE TABLE IF NOT EXISTS incidents( \
        county VARCHAR(30), address VARCHAR(120),\
        occurrence VARCHAR(10), description TEXT);'''
)

conn.commit()
cur.close()
conn.close()

@app.route('/')
def login():
    return render_template('login.html')

    

@app.route('/admin')
def admin():
    return render_template('admin.html')


@app.route('/index', methods=['GET', 'POST'])
def index():

    county = None
    address = None
    occurrence = None
    description = None

    if request.method == 'POST':
        county = request.form.get('county')
        address = request.form['address']
        occurrence = request.form['occurrence']
        description = request.form['description']

    conn = psycopg2.connect(database="rapid_db", user="postgres",
    password=psql_password, host="localhost")  # Replace psql_password with the password for your psql user

    cur = conn.cursor()

    cur.execute(
        '''INSERT INTO incidents (county, address, occurrence, description)
           VALUES (%s, %s, %s, %s);''',
        (county, address, occurrence, description)
    )

    conn.commit()
    cur.close()
    conn.close()
    return render_template('index.html')

@app.route('/resources')
def resources():
    return render_template('resources.html')

if __name__ == '__main__':
   app.run(debug = True)
