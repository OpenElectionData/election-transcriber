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
                    if str(valuelist[0])!= str(int(valuelist[0])):
                        raise ValueError()
                    self.data = int(valuelist[0])
                except ValueError:
                    self.data = None
                    if valuelist[0][0] == '0' and len(valuelist[0])>1:
                        raise ValueError(self.gettext('An integer cannot have leading zeros'))
                    else:
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

class NullableDateField(NullableDateTimeField):
    """
    A DateField where the field can be null if the input data is an empty
    string.
    """

    def process_formdata(self, valuelist):
        if valuelist:
            if valuelist[0] == '':
                self.data = None
            else:
                date_str = ' '.join(valuelist)
                try:
                    self.data = parser.parse(date_str).date()
                except ValueError:
                    self.data = None
                    raise ValidationError(self.gettext('Not a valid date value'))

# checks that something has been inputed - either blank, not legible, or content field
def validate_blank_not_legible(form, field):
    blank = form.data['{0}_blank'.format(field.name)]
    not_legible = form.data['{0}_not_legible'.format(field.name)]
    if field.data == None and not blank and not not_legible:
        message = u'If the "{0}" field is either blank or not legible, \
                please mark the appropriate checkbox'.format(field.name)
        raise ValidationError(message)
    return True
