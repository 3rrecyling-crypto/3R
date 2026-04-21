from django import template

register = template.Library()

@register.filter
def sub(value, arg):
    """Subtracts the argument from the value."""
    try:
        # Tries to subtract the two values directly
        return value - arg
    except (ValueError, TypeError):
        try:
            # If direct subtraction fails, it converts them to floats
            return float(value) - float(arg)
        except (ValueError, TypeError):
            # Returns an empty string if conversion fails
            return ""