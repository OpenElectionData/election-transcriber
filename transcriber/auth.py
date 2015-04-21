# -*- coding: utf-8 -*-
from flask import session as flask_session, redirect, url_for, request, Blueprint, \
    render_template, abort, flash, make_response
from functools import wraps
from flask.ext.security.utils import login_user, logout_user, \
    verify_and_update_password
from flask.ext.security.forms import LoginForm as BaseLoginForm, \
    RegisterForm as BaseRegisterForm
from flask_wtf import Form
from flask_wtf.csrf import CsrfProtect
from wtforms import TextField, PasswordField
from wtforms.validators import DataRequired, Email
from transcriber.models import User
from transcriber.database import db
import os
import json
from uuid import uuid4
from sqlalchemy import func

auth = Blueprint('auth', __name__)

csrf = CsrfProtect()

class LoginForm(BaseLoginForm):
    email = TextField('email', validators=[DataRequired(), Email()])
    password = PasswordField('password', validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        Form.__init__(self, *args, **kwargs)
        self.user = None

    def validate(self):
        rv = Form.validate(self)
        if not rv:
            return False

        user = db.session.query(User)\
            .filter(func.lower(User.email) == func.lower(self.email.data))\
            .first()
        if user is None:
            self.email.errors.append('Email address is not registered')
            return False

        if not verify_and_update_password(self.password.data, user):
            self.password.errors.append('Password is not valid')
            return False

        self.user = user
        return True

class RegisterForm(BaseRegisterForm):
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

        user = db.session.query(User)\
            .filter(func.lower(User.email) == func.lower(self.email.data))\
            .first()
        errors = False
        if user is not None:
            self.email.errors.append('Email address is already registered')
            errors = True
        
        user = db.session.query(User)\
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
