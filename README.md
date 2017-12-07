# Election Transcriber

A tool for digitizing election results data in the form of handwritten digits.

## Setup

The instructions below should get you setup for a development environment. To
get going in production, follow the instructions in
[DEPLOYMENT.md](DEPLOYMENT.md).


1. **Install OS level dependencies:**

  * [Python 3.4+](https://www.python.org/download/)

2. **Clone this repo & install app requirements**

  We recommend using [virtualenv](http://virtualenv.readthedocs.org/en/latest/virtualenv.html) and [virtualenvwrapper](http://virtualenvwrapper.readthedocs.org/en/latest/install.html) for working in a virtualized development environment. [Read how to set up virtualenv](http://docs.python-guide.org/en/latest/dev/virtualenvs/).

  Once you have virtualenvwrapper set up,
  ```bash
  mkvirtualenv et
  git clone git@github.com:datamade/election-transcriber.git
  cd election-transcriber
  pip install -r requirements.txt
  ```
3. **Create a PostgreSQL database for election transcriber**
  If you aren't already running [PostgreSQL](http://www.postgresql.org/), we recommend installing version 9.6 or later.

  ```
  createdb election_transcriber
  ```

4. **Create your own `app_config.py` file**

  ```
  cp transcriber/app_config.py.example transcriber/app_config.py
  ```

  You will need to change, at minimum:
  - `DB_USER` and `DB_PW` to reflect your PostgreSQL username/password (by default, the username is your computer name & the password is '')
  - `S3_BUCKET` to tell the application where to look for your cache of images
    to transcribe
  - `AWS_CREDENTIALS_PATH` tells the application where to find the CSV file
    with your AWS credentials in it. By default, the application looks for
    a file called `credenitals.csv` in the root folder of the project.

  You can also change the username, email and password for the initial user roles, defined by `ADMIN_USER`, `MANAGER_USER`, and `CLERK_USER`

5. **Create your own `alembic.ini` file**

  ```
  cp alembic.ini.example alembic.ini
  ```
  You will need to change, at minimum, `user` & `pass` (to reflect your PostgreSQL username/password) on line 6

6. **Initialize the database**

  ```bash
  alembic upgrade head
  ```

7. **Import images**
  ```bash
  python update_images.py
  ```

8. **Run the app**

  ```bash
  python runserver.py
  ```

9. **In another terminal, run the worker**

  ```bash
  python run_queue.py
  ```

Once the server is running, navigate to http://localhost:5000/

## Syncing images between Google Drive and AWS

There is a script in the root folder of the project called
`syncDriveFolder.py`. As you might guess, it's the script that is responsible
for syncing files from a Google Drive folder to an AWS S3 bucket. In order for
this to work, you'll need to take a couple steps:

**Setup a Service Account in your Google Developer Console**

* Navigate to https://developers.google.com and login if you're not already
  logged in.
* Create a project
