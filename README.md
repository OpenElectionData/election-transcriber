# Election Transcriber

A tool for digitizing election results data in the form of handwritten digits. 

### Setup

**Install OS level dependencies:** 

* [Python 2.7](https://www.python.org/download/releases/2.7/)

**Install app requirements**

```bash
git clone git@github.com:datamade/election-transcriber.git
cd election-transcriber
pip install -r requirements.txt
```

Create a PostgreSQL database for election_transcriber. (If you aren't
  already running [PostgreSQL](http://www.postgresql.org/), we recommend
  installing version 9.3 or later.)

```
createdb election_transcriber
```

Create your own `app_config.py` file:

```
cp transcriber/app_config.py.example transcriber/app_config.py
```

You will want to change, at the minimum, the following `app_config.py` fields:

* `DB_CONN`: edit this field to reflect your PostgreSQL
  username, server hostname, port, and database name. 

* `DEFAULT_USER`: change the username, email and password on the administrator account you will use on Plenario locally.

Initialize the database: 

```bash
python init_db.py
```

Finally, run the app:

```bash
python runserver.py
```

Once the server is running, navigate to http://localhost:5000/