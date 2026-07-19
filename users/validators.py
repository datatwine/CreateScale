from better_profanity import profanity
from django.core.exceptions import ValidationError

profanity.load_censor_words()


def validate_no_profanity(value):
    if profanity.contains_profanity(value):
        raise ValidationError("This field contains inappropriate language.")
