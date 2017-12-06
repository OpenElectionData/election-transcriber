# Deploying the NDI Election Transcriber Tool

The instructions below reflect one, rather opinionated, way of setting up the
Election Transcriber tool on a production server. With the exception of the
database, the specific parts and pieces that are used here could more than
likely be swapped out for other similar parts and work just as well. In the
end, we'll need to setup a web server ([Nginx](https://nginx.org)), something
to daemonize the application and the process that handles delayed work
([Supervisor](http://supervisord.org/)), and
[PostgreSQL](https://postgresql.org).\

**Note** The instructions below will work on a modern Ubuntu variant
(14.04+) or on Debian 8 (jessie) or better.

**Another note** The package managers for Linux distributions often don't have the most recent
versions of many packages available to them when they are released. Since we
want to get the most recent stable version of the packages we're installing,
we'll start each of these sections by showing the package manager how to find
the most recent stable version of these packages without needing to build them
from source. One thing that you will need to know for this is the code name of
your Linux distribution. If you don't already know that, you check check
[here](https://en.wikipedia.org/wiki/Ubuntu_version_history#Release_history)
for Ubuntu or [here](https://en.wikipedia.org/wiki/Debian_version_history#Release_history) for Debian.

**Another another note** These instructions assume you already have a server
setup and are ready to start installing things on it. All of the steps below
should be performed on the server itself. If you're not sure how to connect via
ssh to your server, refer to the documentation (hopefully) provided by the
host.

### Install Nginx

[Reference](http://nginx.org/en/linux_packages.html)_

* Make sure that you have `wget` installed:
```
sudo apt-get install wget
```

* Download the package signing key from the Nginx repository

```
wget http://nginx.org/keys/nginx_signing.key
```

* Let your package manager know that you're OK installing packages signed with
  that key

```
sudo apt-key add nginx_signing.key
```

* Add a file to `/etc/apt/sources.list.d` called `nginx.list`
* For Ubuntu, replace the `[codename]` blocks in the examples below with the code name of your
   particular distribution and add it to the file you created in the last step.

```
deb http://nginx.org/packages/ubuntu/ [codename] nginx
deb-src http://nginx.org/packages/ubuntu/ [codename] nginx
```

* For Debian, do the same thing only with this:

```
deb http://nginx.org/packages/debian/ [codename] nginx
deb-src http://nginx.org/packages/debian/ [codename] nginx
```

* Now update the package manager and install nginx

```
sudo apt-get update
sudo apt-get install nginx
```

### Install PostgreSQL

[Reference](https://wiki.postgresql.org/wiki/Apt)

* Make a file in `/etc/apt/sources.list.d` called `pgdg.list`
* Add the following line to that file replacing `[codename]` with the code name
  of your distribution:

```
deb http://apt.postgresql.org/pub/repos/apt/ [codename]-pgdg main
```

* Make sure that you have `wget` and `ca-certificates` installed:

```
sudo apt-get install wget ca-certificates
```

* Download the PostgreSQL signing key and import let your package manager know
  you're OK with it:

```
wget https://www.postgresql.org/media/keys/ACCC4CF8.asc
sudo apt-key add ACCC4CF8.asc
```

* Update the package manager and install PostgreSQL 9.6

```
sudo apt-get update
sudo apt-get install postgresql-9.6
```

### Install Supervisor

The version that ships with modern, stable Linux distributions is OK for our
purposes so we can just make sure the package manager is up to date and install
it:

```
sudo apt-get update
sudo apt-get install supervisor
```

### Check for and maybe install Python 3

If you're using one of the Linux distributions that I mentioned above, you
should already have Python 3 either installed or easily installable. To check,
you can just type `python3` and if you get an error saying that it's an "uknown
command", then you can run:

```
sudo apt-get install python3
```

Either way, we'll need to get the Python 3 development package to build some of
the dependencies that the application has. Install that like so:

```
sudo apt-get install python3-dev
```

### Configure Nginx

**Note** Before starting on this step make sure that you have a host name setup
and the DNS is configured and resolving to the IP address of the server. If
that's not the case yet, it's OK to skip this step for now and come back later.

* Make a file in `/etc/nginx/conf.d/` called `transcriber.conf` and put the
  following in there replacing `[hostname]` with the domain name that you
  eventually want to use for the application.

```
server {
    listen 80;
    server_name [hostname];

    location ~ .well-known/acme-challenge {
        root /usr/share/nginx/html;
        default_type text/plain;
    }

    location / {
        return 301 https://[hostname]$request_uri;
    }

}
```

* Restart nginx

```
sudo service nginx restart
```

* Install Certbot using the instructions for your setup found [here](https://certbot.eff.org/)
* Install the certificate for your hostname. (Replace [hostname] with the
  hostname you put into the configuration above)

```
sudo certbot certonly --webroot -w /usr/share/nginx/html -d [hostname]
```

Part of the cryptographic handshake that happens when a user loads your site
over a TLS connection involves generating very large prime numbers. We'll want
these numbers to be larger than the default settings so we'll generate
a parameter file that allows for that to happen:

```
openssl dhparam -out dhparams.pem 2048
sudo mv dhparams.pem /etc/ssl/private/
sudo chown root.root /etc/ssl/private/dhparams.pem
```

* Next, replace the contents of the Nginx configuration you made above with
  this (again replacing `[hostname]` with the actual host name you're using)

```
server {
    listen 443;
    server_name [hostname];
    access_log /var/log/nginx/{{ appname }}-access.log;
    error_log /var/log/nginx/{{ appname }}-error.log;

    ssl on;
    ssl_certificate /etc/letsencrypt/live/[hostname]/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/[hostname]/privkey.pem;

    ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
    ssl_ciphers 'ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-DSS-AES128-GCM-SHA256:kEDH+AESGCM:ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA:ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-RSA-AES256-SHA:ECDHE-ECDSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-DSS-AES128-SHA256:DHE-RSA-AES256-SHA256:DHE-DSS-AES256-SHA:DHE-RSA-AES256-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256:AES128-SHA:AES256-SHA:AES:CAMELLIA:DES-CBC3-SHA:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!MD5:!PSK:!aECDH:!EDH-DSS-DES-CBC3-SHA:!EDH-RSA-DES-CBC3-SHA:!KRB5-DES-CBC3-SHA';

    ssl_prefer_server_ciphers on;

    ssl_dhparam /etc/ssl/private/dhparams.pem;

    gzip on;

    gzip_http_version  1.1;

    gzip_comp_level    5;

    gzip_min_length    256;

    gzip_proxied       any;

    gzip_vary          on;

    gzip_types
      application/atom+xml
      application/javascript
      application/json
      application/rss+xml
      application/vnd.ms-fontobject
      application/x-font-ttf
      application/x-web-app-manifest+json
      application/xhtml+xml
      application/xml
      font/opentype
      image/svg+xml
      image/x-icon
      text/css
      text/plain
      text/x-component;

    location / {
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $http_host;
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
	    proxy_read_timeout 300s;
    }

    location /static {
        alias /home/datamade/election-transcriber/transcriber/static;
    }

}

server {
    listen 80;
    server_name [hostname];

    location ~ .well-known/acme-challenge {
       root /usr/share/nginx/html;
       default_type text/plain;
    }

    location / {
        return 301 https://[hostname]$request_uri;
    }
}
```

* Restart Nginx again for the configuration to take effect:

```
sudo service nginx restart
```

### Configure Supervisor

* Make a file in `/etc/supervisor/conf.d/` called `transcriber.conf` and put
  the following into it:

```
[program:transcriber]
stdout_logfile=/tmp/transcriber-gunicorn-out.log
stdout_logfile_maxbytes=10MB
stderr_logfile=/tmp/transcriber-gunicorn-err.log
stderr_logfile_maxbytes=10MB
directory=/home/datamade/election-transcriber
process_name=transcriber
user=datamade
command=/home/datamade/.virtualenvs/transcriber/bin/gunicorn -t 301 --log-level info -b 127.0.0.1:5000 runserver:app

[program:transcriber-worker]
stdout_logfile=/tmp/transcriber-gunicorn-out.log
stdout_logfile_maxbytes=10MB
stderr_logfile=/tmp/transcriber-gunicorn-err.log
stderr_logfile_maxbytes=10MB
directory=/home/datamade/election-transcriber
process_name=worker
user=datamade
command=/home/datamade/.virtualenvs/transcriber/bin/python run_queue.py
```

* We'll wait to restart Supervisor until we have the code in place and ready to
  go.

### Configure PostgreSQL

* Replace the contents of `/etc/postgresql/9.6/main/pg_hba.conf` with:

```
local all all trust
host all all 127.0.0.1/32 trust
```

* Restart PostgreSQL for the changes to take effect:

```
sudo service postgresql restart
```

**Note** This will make connections to your database without a password
possible as long as you are logged into the server. If you are not comfortable
with this or if there is some reason that you need to open up the database to
the world, please consult the [PostgreSQL docs](https://www.postgresql.org/docs/9.6/static/auth-pg-hba-conf.html).

* Create a user for your application to use

```
createuser -U postgres datamade
```

* Create a database for your application to use

```
createdb -U postgres -O datamade transcriber
```

### Setup a user on the operating system to use to run the application

Because this application will be exposed to the internet and because,
ultimately, the operating system will run this application as a user, we'll
need to setup a user that doesn't have very many privileges to use to run it.
The thinking here is that if there is some kind of unknown exploit that is
latent within the code that is running, at least it that code will not be
executed by a user that can cause any harm to the server itself.

There is a simple, one-line command that you can run to do this:

```
sudo useradd -d /home/datamade -m -r datamade
```

You can change `datamade` to whatever you want it to be but that's where that
user's home directory will be (which is where we'll put the code) and that's
what the user will be called. In the examples that follow as well as in the
configuration files that are above, you'll need to switch out `datamade` for
whatever you choose.

### Setup a Python Virtual Environment

* Install pip

```
sudo apt-get install python3-pip
```

* Install virtualenvwrapper

```
sudo pip3 install virtualenvwrapper
```

* Switch to the `datamade` user

```
sudo su datamade
cd /home/datamade
```

* Add the following lines to the end of the .bashrc file found in
  the `datamade` user's home directory. This will make it so that whenever you
  are using the `datamade` user on the server, you will have access to the
  `virtualenvwrapper` commands without needing to take extra steps.

```
VIRTUALENVWRAPPER_PYTHON=/usr/bin/python3
source /usr/local/bin/virtualenvwrapper.sh
```

* Make sure you have access to the virtualenvwrapper commands and make
  a virtual environment

```
source /usr/local/bin/virtualenvwrapper.sh
mkvirtualenv transcriber
```

### Clone the code repository and install the requirements

* Make sure you have `git` installed:

```
sudo apt-get install git-core
```

* Switch to the `datamade` user:

```
sudo su datamade
cd /home/datamade
```

* Activate the virtual environment

```
workon transcriber
```


* Clone the repository and switch into the directory it creates

```
git clone https://github.com/datamade/election-transcriber.git
cd election-transcriber
```

* Use `pip` to install the requirements

```
pip install -r requirements.txt
```

* Initialize the tables in the database

```
alembic upgrade head
```

* Import any images that you might already be stored in your S3 Bucket.

```
python update_images.py
```

### Run the application

As mentioned above, we waited to restart Supervisor. Now is the time:

```
sudo service supervisor restart
```

And with that, you should be able to visit your new application on the internet
at your chosen host name. Enjoy!
