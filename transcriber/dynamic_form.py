from wtforms.validators import ValidationError
from wtforms.fields import IntegerField
from wtforms.ext.dateutil.fields import DateTimeField, DateField
from dateutil import parser

class BlankValidator(object):

    def __init__(self, message=None):
        self.message = message

    def __call__(self, form, field):
        blank = form.data['{0}_blank'.format(field.name)]
        not_legible = form.data['{0}_not_legible'.format(field.name)]
        if not field.data and not blank and not not_legible:
            raise ValidationError(self.message)

class TranscriberIntegerField(IntegerField):

    def process_formdata(self, valuelist):
        if valuelist:
            try:
                self.data = int(valuelist[0])
            except ValueError:
                self.data = None
                message = u'The "{0}" field expects a number. If it is blank or \
                        not legible, mark the appropriate box'.format(self.name)
                raise ValidationError(self.gettext(message))

class TranscriberDateTimeField(DateTimeField):

    def process_formdata(self, valuelist):
        message = u'The "{0}" field expects a date and time. If it is blank or \
                not legible, mark the appropriate box'
        if valuelist:
            date_str = ' '.join(valuelist)
            if not date_str:
                self.data = None
                raise ValidationError(self.gettext(message))

            try:
                self.data = parser.parse(date_str, **parse_kwargs)
            except ValueError:
                self.data = None
                raise ValidationError(self.gettext(message))

class TranscriberDateField(TranscriberDateTimeField):
    """
    Same as the DateTimeField, but stores only the date portion.
    """
    def __init__(self, label=None, validators=None, parse_kwargs=None,
                 display_format='%Y-%m-%d', **kwargs):
        super(DateField, self).__init__(label, validators, parse_kwargs=parse_kwargs, display_format=display_format, **kwargs)

    def process_formdata(self, valuelist):
        super(DateField, self).process_formdata(valuelist)
        if self.data is not None and hasattr(self.data, 'date'):
            self.data = self.data.date()
