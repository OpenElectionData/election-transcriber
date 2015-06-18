# Election Transcriber

A tool for digitizing election results data in the form of handwritten digits. 

## Setup

1. **Install OS level dependencies:** 

  * [Python 2.7](https://www.python.org/download/releases/2.7/)

2. **Clone this repo & install app requirements**

  ```bash
  git clone git@github.com:datamade/election-transcriber.git
  cd election-transcriber
  pip install -r requirements.txt
  ```
3. **Create a PostgreSQL database for election_transcriber**  
  If you aren't already running [PostgreSQL](http://www.postgresql.org/), we recommend installing version 9.3 or later.

  ```
  createdb election_transcriber
  ```

4. **Create your own `app_config.py` file**

  ```
  cp transcriber/app_config.py.example transcriber/app_config.py
  ```

  You will need to change, at minimum, `DB_USER` and `DB_PW` (to reflect your PostgreSQL username/password)

  You can also change the username, email and password for `ADMIN_USER` - this is the administrator account you will use locally
  
5. **Create your own `alembic.ini` file**

  ```
  cp alembic.ini.example alembic.ini
  ```
  You will need to change, at minimum, `user` & `pass` (to reflect your PostgreSQL username/password) on line 6

6. **Initialize the database**  

  ```bash
  python init_db.py
  ```

7. **Finally, run the app**  

  ```bash
  python runserver.py
  ```
  Once the server is running, navigate to http://localhost:5000/
