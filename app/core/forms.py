from flask_wtf import FlaskForm, RecaptchaField
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email


class ContactForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email Address', validators=[DataRequired(),
                                                     Email()])
    phone = StringField('Phone (optional)')
    message = TextAreaField('Message', validators=[DataRequired()],
                            render_kw={'rows': 5})
    recaptcha = RecaptchaField()
    submit = SubmitField('Send Message')