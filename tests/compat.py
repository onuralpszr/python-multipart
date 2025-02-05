import functools
import os
import re
import sys
import types


def ensure_in_path(path):
    """
    Ensure that a given path is in the sys.path array
    """
    if not os.path.isdir(path):
        raise RuntimeError("Tried to add nonexisting path")

    def _samefile(x, y):
        try:
            return os.path.samefile(x, y)
        except OSError:
            return False
        except AttributeError:
            # Probably on Windows.
            path1 = os.path.abspath(x).lower()
            path2 = os.path.abspath(y).lower()
            return path1 == path2

    # Remove existing copies of it.
    for pth in sys.path:
        if _samefile(pth, path):
            sys.path.remove(pth)

    # Add it at the beginning.
    sys.path.insert(0, path)


# Check if pytest is imported.  If so, we use it to create marking decorators.
# If not, we just create a function that does nothing.
try:
    import pytest
except ImportError:
    pytest = None

if pytest is not None:
    slow_test = pytest.mark.slow_test
    xfail = pytest.mark.xfail

else:

    def slow_test(x):
        return x

    def xfail(*args, **kwargs):
        if len(args) > 0 and isinstance(args[0], types.FunctionType):
            return args[0]

        return lambda x: x


# We don't use the pytest parametrizing function, since it seems to break
# with unittest.TestCase subclasses.
def parametrize(field_names, field_values):
    # If we're not given a list of field names, we make it.
    if not isinstance(field_names, (tuple, list)):
        field_names = (field_names,)
        field_values = [(val,) for val in field_values]

    # Create a decorator that saves this list of field names and values on the
    # function for later parametrizing.
    def decorator(func):
        func.__dict__["param_names"] = field_names
        func.__dict__["param_values"] = field_values
        return func

    return decorator


# This is a metaclass that actually performs the parametrization.
class ParametrizingMetaclass(type):
    IDENTIFIER_RE = re.compile("[^A-Za-z0-9]")

    def __new__(klass, name, bases, attrs):
        new_attrs = attrs.copy()
        for attr_name, attr in attrs.items():
            # We only care about functions
            if not isinstance(attr, types.FunctionType):
                continue

            param_names = attr.__dict__.pop("param_names", None)
            param_values = attr.__dict__.pop("param_values", None)
            if param_names is None or param_values is None:
                continue

            # Create multiple copies of the function.
            for i, values in enumerate(param_values):
                assert len(param_names) == len(values)

                # Get a repr of the values, and fix it to be a valid identifier
                human = "_".join([klass.IDENTIFIER_RE.sub("", repr(x)) for x in values])

                # Create a new name.
                # new_name = attr.__name__ + "_%d" % i
                new_name = attr.__name__ + "__" + human

                # Create a replacement function.
                def create_new_func(func, names, values):
                    # Create a kwargs dictionary.
                    kwargs = dict(zip(names, values))

                    @functools.wraps(func)
                    def new_func(self):
                        return func(self, **kwargs)

                    # Manually set the name and return the new function.
                    new_func.__name__ = new_name
                    return new_func

                # Actually create the new function.
                new_func = create_new_func(attr, param_names, values)

                # Save this new function in our attrs dict.
                new_attrs[new_name] = new_func

            # Remove the old attribute from our new dictionary.
            del new_attrs[attr_name]

        # We create the class as normal, except we use our new attributes.
        return type.__new__(klass, name, bases, new_attrs)


# This is a class decorator that actually applies the above metaclass.
def parametrize_class(klass):
    return ParametrizingMetaclass(klass.__name__, klass.__bases__, klass.__dict__)
