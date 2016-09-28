import time
import os
import json
import fnmatch
import sys
import itertools
from importlib import util as import_util

migrations_dir_ = 'migrations/'
state_file_ = migrations_dir_ + '.state'


def create(name, migrations_dir=migrations_dir_, template_file=None):
    if template_file is None:
        template = """\
def up():
    pass


def down():
    pass
"""
    else:
        with open(template_file, 'r') as file:
            template = file.read()

    migrations_dir = (
        lambda path: path if path[-1] == '/' else path + '/'
    )(migrations_dir)

    os.makedirs(migrations_dir, 0o775, exist_ok=True)
    filename = '{path}{time:.0f}_{name}.py'.format(
        path=migrations_dir,
        time=time.time(),
        name=name.replace(' ', '_')
    )
    with open(filename, 'w') as file:
        file.write(template)
    print('File \'{}\' has been created.'.format(filename))


def perform(
        direction='up',
        target=None,
        migrations_dir=migrations_dir_,
        state_file=state_file_):

    if direction != 'up' and direction != 'down':
        raise MigrationError('direction {} is invalid'.format(direction))

    if isinstance(target, str) and target.isdecimal():
        number = int(target)
        if number > 0:
            target = number

    migrations_dir = (
        lambda path: path if path[-1] == '/' else path + '/'
    )(migrations_dir)

    available = get_all_migrations(migrations_dir)
    performed = get_performed_migrations(state_file)
    check_integrity(available, performed)
    migrations = get_migrations(available, performed, direction, target)

    def run_and_show_time():
        for migration in migrations:
            yield run(migration, migrations_dir, direction)

    sys.path.insert(0, os.getcwd())
    total_time = sum(
        run_and_show_time()
    )
    del sys.path[0]

    set_state(direction, performed, migrations, state_file)

    print('\nMigrations have been {action}. Total time: {time:.3f}s'.format(
        action='reverted' if direction == 'down' else 'applied',
        time=total_time
    ))


def show(migrations_dir=migrations_dir_, state_file=state_file_):
    performed = get_performed_migrations(state_file)
    available = get_all_migrations(migrations_dir)
    check_integrity(available, performed)
    new = available[len(performed):]

    performed_header = 'Applied migrations:'
    new_header = 'New migrations:'

    performed_str = '\n'.join([
        '-' * len(performed_header),
        performed_header,
        '-' * len(performed_header),
        '\n'.join(performed),
    ]) if performed else ''

    new_str = '\n'.join([
        '-' * len(new_header),
        new_header,
        '-' * len(new_header),
        '\n'.join(new),
    ]) if new else ''

    if performed_str and new_str:
        print(performed_str + '\n' + new_str)
    else:
        print(performed_str + new_str)


def get_all_migrations(migrations_dir):
    try:
        available = [
            file
            for file in os.listdir(migrations_dir)
            if fnmatch.fnmatch(file, '*.py')
        ]
        available.sort()
        return available
    except FileNotFoundError as e:
        raise MigrationError('no migrations found') from e


def get_performed_migrations(state_file):
    try:
        with open(state_file, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return []


def check_integrity(available, performed):
    for available_item, performed_item in itertools.zip_longest(
            available, performed
    ):
        if available_item != performed_item and performed_item is not None:
            break
    else:
        return

    msg = """\
migration order is corrupt.
Expected '{performed}' in the directory.
Got '{available}' instead.
You must resolve the conflict manually.
For more info run `migrate show`"""
    msg = msg.format(performed=performed_item, available=available_item)
    raise MigrationError(msg)


def get_migrations(available, performed, direction, target):
    if direction == 'down':
        migrations = performed.copy()
        migrations.reverse()
    else:
        migrations = available[len(performed):]

    if target is None:
        if direction == 'down':
            return migrations[:1]
        return migrations
    if isinstance(target, int):
        migrations = migrations[:target]
    else:
        for index, migration in enumerate(migrations):
            if migration == target:
                break
        else:
            raise MigrationError(
                'migration with provided name {} not found'.format(target)
            )
        migrations = migrations[:index + 1]

    return migrations


def run(name, directory, direction):
    import_spec = import_util.spec_from_file_location(
        name,
        directory + name
    )
    module = import_util.module_from_spec(import_spec)
    import_spec.loader.exec_module(module)

    print('{action} {name}...'.format(
        action='Reverting' if direction == 'down' else 'Applying',
        name=name,
    ), end='', flush=True)

    action = getattr(module, direction)
    started = time.time()
    action()
    duration = time.time() - started

    print('done (time: {:.3f}s)'.format(duration))
    return duration


def set_state(direction, old_state, migrations, state_file):
    if direction == 'down':
        state = old_state[:-len(migrations)]
    else:
        state = old_state + migrations
    with open(state_file, 'w') as file:
        json.dump(
            state,
            file,
            indent=2
        )


class MigrationError(Exception):
    def __init__(self, message, *args):
        super(MigrationError, self).__init__(message, *args)
        self.message = message

    def __str__(self):
        return 'Error: {}.'.format(self.message)
