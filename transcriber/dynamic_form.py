from wtforms.validators import ValidationError
from dateutil import parser

def validate_blank_not_legible(form, field):
    blank = form.data['{0}_blank'.format(field.name)]
    not_legible = form.data['{0}_not_legible'.format(field.name)]
    if not field.data and not blank and not not_legible:
        message = u'If the "{0}" field is either blank or not legible, \
                please mark the appropriate checkbox'.format(field.name)
        raise ValidationError(message)
    return True

def validate_integer(form, field):
    validate_blank_not_legible(form, field)
    data = form.data[field.name]
    try:
        data = int(data)
    except ValueError:
        message = u'The "{0}" field expects a number. If it is blank or \
                not legible, mark the appropriate box'.format(field.name)
        raise ValidationError(message)
    return True

def validate_date(form, field):
    validate_blank_not_legible(form, field)
    data = form.data[field.name]
    try:
        data = parser.parse(data)
    except ValueError:
        raise ValidationError(message)
    return True
