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
for syncing files from a Google Drive folder to an AWS S3 bucket.

* Follow the instructions [here](https://developers.google.com/identity/protocols/OAuth2ServiceAccount#creatinganaccount) to get a Google Service Account setup.
* You should end up with a JSON file that looks like this:

```
{
  "type": "service_account",
  "project_id": "[name of the project]",
  "private_key_id": "[long hash]",
  "private_key": "[very very long hash]",
  "client_email": "some-user@project-name.iam.gserviceaccount.com",
  "client_id": "[long number]",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://accounts.google.com/o/oauth2/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "[long URL]"
}
```

**As was explained in the part where you download that, the contents of this file
should be kept secret.**

* Copy the `client_email` address from that JSON file.
* In a browser, navigate to the Google Drive folder where your images are.
* Click the icon next to the folder's name to open the sharing preferences and
  share the folder with that email address. You won't need to send
  a notification because it won't really go anywhere anyways. You'll also only
  need to give that account "View only" permissions.
