from wtforms.validators import ValidationError
from wtforms.fields import IntegerField, DateTimeField
from dateutil import parser

class NullableIntegerField(IntegerField):
    """
    An IntegerField where the field can be null if the input data is an empty
    string.
    """

    def process_formdata(self, valuelist):
        if valuelist:
            if valuelist[0] == '':
                self.data = None
            else:
                try:
                    self.data = int(valuelist[0])
                except ValueError:
                    self.data = None
                    raise ValueError(self.gettext('Not a valid integer value'))


class NullableDateTimeField(DateTimeField):
    """
    A DateTimeField where the field can be null if the input data is an empty
    string.
    """

    def process_formdata(self, valuelist):
        if valuelist:
            if valuelist[0] == '':
                self.data = None
            else:
                date_str = ' '.join(valuelist)
                try:
                    self.data = parser.parse(date_str)
                except ValueError:
                    self.data = None
                    raise ValidationError(self.gettext('Not a valid datetime value'))

# checks that something has been inputed - either blank, not legible, or content field
def validate_blank_not_legible(form, field):
    blank = form.data['{0}_blank'.format(field.name)]
    not_legible = form.data['{0}_not_legible'.format(field.name)]
    if not field.data and not blank and not not_legible:
        message = u'If the "{0}" field is either blank or not legible, \
                please mark the appropriate checkbox'.format(field.name)
        raise ValidationError(message)
    return True

# if blank or not legible checked, return true
def require_content_validation(form, field):
    blank = form.data['{0}_blank'.format(field.name)]
    not_legible = form.data['{0}_not_legible'.format(field.name)]
    if blank or not_legible:
        return False
    else:
        return True

def validate_integer(form, field):
    validate_blank_not_legible(form, field)
    data = form.data[field.name]
    if data and require_content_validation(form, field):
        try:
            data = int(data)
        except ValueError:
            message = u'The "{0}" field expects a number. If it is blank or \
                    not legible, mark the appropriate box'.format(field.name)
            raise ValidationError(message)
    return True