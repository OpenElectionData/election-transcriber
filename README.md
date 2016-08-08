# Election Transcriber

A tool for digitizing election results data in the form of handwritten digits. 

## Setup

1. **Install OS level dependencies:** 

  * [Python 2.7](https://www.python.org/download/releases/2.7/)

2. **Clone this repo & install app requirements**

  We recommend using [virtualenv](http://virtualenv.readthedocs.org/en/latest/virtualenv.html) and [virtualenvwrapper](http://virtualenvwrapper.readthedocs.org/en/latest/install.html) for working in a virtualized development environment. [Read how to set up virtualenv](http://docs.python-guide.org/en/latest/dev/virtualenvs/).

  Once you have virtualenvwrapper set up,
  ```bash
  mkvirtualenv et
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

  You will need to change, at minimum:
  - `DB_USER` and `DB_PW` to reflect your PostgreSQL username/password (by default, the username is your computer name & the password is '')
  - `DOCUMENTCLOUD_USER` and `DOCUMENTCLOUD_PW` to reflect your DocumentCloud credentials

  You can also change the username, email and password for the initial user roles, defined by `ADMIN_USER`, `MANAGER_USER`, and `CLERK_USER`
  
5. **Create your own `alembic.ini` file**

  ```
  cp alembic.ini.example alembic.ini
  ```
  You will need to change, at minimum, `user` & `pass` (to reflect your PostgreSQL username/password) on line 6

6. **Initialize the database**  

  ```bash
  python init_db.py
  ```

7. **Import document cloud images**
  ```bash
  python update_images.py
  ```

8. **Finally, run the app**  

  ```bash
  python runserver.py
  ```
  Once the server is running, navigate to http://localhost:5000/
