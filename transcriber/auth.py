# -*- coding: utf-8 -*-
from flask import session as flask_session, redirect, url_for, request, Blueprint, \
    render_template, abort, flash, make_response
from functools import wraps
from flask.ext.security.utils import login_user, logout_user
from flask.ext.security.registerable import register_user
from flask_wtf import Form
from flask_wtf.csrf import CsrfProtect
from wtforms import TextField, PasswordField
from wtforms.validators import DataRequired, Email
from transcriber.database import db_session
from transcriber.models import User
import os
import json
from uuid import uuid4
from sqlalchemy import func

auth = Blueprint('auth', __name__)

csrf = CsrfProtect()

class LoginForm(Form):
    email = TextField('email', validators=[DataRequired(), Email()])
    password = PasswordField('password', validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        Form.__init__(self, *args, **kwargs)
        self.user = None

    def validate(self):
        rv = Form.validate(self)
        if not rv:
            return False

        user = db_session.query(User)\
            .filter(func.lower(User.email) == func.lower(self.email.data))\
            .first()
        if user is None:
            self.email.errors.append('Email address is not registered')
            return False

        if not user.check_password(user.name, self.password.data):
            self.password.errors.append('Password is not valid')
            return False

        self.user = user
        return True

class RegisterForm(Form):
    name = TextField('username', validators=[DataRequired()])
    email = TextField('email', validators=[DataRequired(), Email()])
    password = PasswordField('password', validators=[DataRequired()])
    
    def __init__(self, *args, **kwargs):
        Form.__init__(self, *args, **kwargs)
        self.user = None

    def validate(self):
        rv = Form.validate(self)
        if not rv:
            return False

        user = db_session.query(User)\
            .filter(func.lower(User.email) == func.lower(self.email.data))\
            .first()
        errors = False
        if user is not None:
            self.email.errors.append('Email address is already registered')
            errors = True
        
        user = db_session.query(User)\
            .filter(func.lower(User.name) == func.lower(self.name.data))\
            .first()
        if user is not None:
            self.name.errors.append('Username is already registered')
            errors = True
        
        if errors:
            return False

        return True
    
    def as_dict(self):
        return {'name': self.name.data, 
                'password': self.password.data, 
                'email': self.email.data}

@auth.route('/login/', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = form.user
        login_user(user)
        return redirect(request.args.get('next') or url_for('views.index'))
    email = form.email.data
    return render_template('login.html', form=form, email=email)

@auth.route('/logout/')
def logout():
    logout_user()
    response = redirect(url_for('auth.login'))
    response.set_cookie('session', '', expires=0)
    return response

@auth.route('/register/', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = register_user(**form.as_dict())
        form.user = user
        return redirect('/')
    return render_template('security/register_user.html', register_user_form=form)

