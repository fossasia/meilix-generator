"""A simple tasks manager using the Dropbox Datastore API.

This example requires Python 2.7 (for OrderedDict).

This uses the same data model as the JavaScript tutorial example.

The code is somewhat uncharacteristic for Flask apps (e.g. it doesn't
use template files).  The advantage of this style is that the entire
app is one file, and it's easier to follow what is going on.
"""

from collections import OrderedDict  # Requires Python 2.7.
from threading import Lock
from weakref import WeakValueDictionary

from flask import Flask, request, session, redirect, url_for, abort, render_template_string

from dropbox.client import DropboxClient, DropboxOAuth2Flow, ErrorResponse
from dropbox.datastore import DatastoreManager, Date, DatastoreError

# Fill these in!  See https://www.dropbox.com/developers/apps
DROPBOX_APP_KEY = 'kf7a9zsqzdxw12k'
DROPBOX_APP_SECRET = 'rhafv0flrvee6l7'

# Flask options.  These are read by Flask.
DEBUG = True
SECRET_KEY = 'development key'

# Create application object.
app = Flask(__name__)
app.config.from_object(__name__)
app.config.from_envvar('TASKS_SETTINGS', silent=True)


# Application routes and helper.

@app.route('/')
def home():
    with get_access_token_lock():
        datastore = open_datastore(refresh=True)
        if not datastore:
            return '<a href="%s">Link to Dropbox</a>' % url_for('dropbox_auth_start')
        return render_template_string(
            '''
            <h1>My Tasks</h1>
            <ul>
                {% for task in tasks %}
                <li>
                    {% if task.get('completed') %}
                        [&#x2713;] {{ task.get('taskname') }}
                        (<a href="{{ url_for('uncomplete', id=task.get_id())}}">mark incomplete</a>)
                        (<a href="{{ url_for('delete', id=task.get_id()) }}">delete</a>)
                    {% else %}
                        [ &nbsp; ] {{ task.get('taskname') }}
                        (<a href="{{ url_for('complete', id=task.get_id())}}">mark complete</a>)
                        (<a href="{{ url_for('delete', id=task.get_id()) }}">delete</a>)
                    {% endif %}
                </li>
                {% endfor %}
            </ul>
            <form method="post" action="{{ url_for('add') }}">
                <input type="text" name="name" />
                <input type="submit" name="Add" />
            </form>
            <a href="{{ url_for('dropbox_logout') }}">Log out</a>
            ''',
            tasks=sorted(datastore.get_table('tasks').query(),
                         key=lambda record: record.get('created')))


@app.route('/add', methods=['POST'])
def add():
    taskname = request.form.get('name')
    if taskname:
        with get_access_token_lock():
            datastore = open_datastore()
            if datastore:
                table = datastore.get_table('tasks')
                def txn():
                    table.insert(completed=False, taskname=taskname, created=Date())
                try:
                    datastore.transaction(txn, max_tries=4)
                except DatastoreError:
                    return 'Sorry, something went wrong. Please hit back or reload.'
    return redirect(url_for('home'))


@app.route('/delete')
def delete():
    id = request.args.get('id')
    if id:
        with get_access_token_lock():
            datastore = open_datastore()
            if datastore:
                table = datastore.get_table('tasks')
                def txn():
                    record = table.get(id)
                    if record:
                        record.delete_record()
                try:
                    datastore.transaction(txn, max_tries=4)
                except DatastoreError:
                    return 'Sorry, something went wrong. Please hit back or reload.'
    return redirect(url_for('home'))


@app.route('/complete')
def complete():
    return change_completed(True)


@app.route('/uncomplete')
def uncomplete():
    return change_completed(False)


def change_completed(completed):
    id = request.args.get('id')
    if id:
        with get_access_token_lock():
            datastore = open_datastore()
            if datastore:
                table = datastore.get_table('tasks')
                def txn():
                    record = table.get(id)
                    if record:
                        record.update(completed=completed)
                try:
                    datastore.transaction(txn, max_tries=4)
                except DatastoreError:
                    return 'Sorry, something went wrong. Please hit back or reload.'
    return redirect(url_for('home'))


# Locking per access token.
locks = WeakValueDictionary()
meta_lock = Lock()

def get_access_token_lock():
    access_token = session.get('access_token')
    if not access_token:
        return Lock()  # Dummy lock.
    with meta_lock:
        lock = locks.get(access_token)
        if lock is None:
            locks[access_token] = lock = Lock()
        return lock


# LRU cache used by open_datastore.
cache = OrderedDict()

def open_datastore(refresh=False):
    access_token = session.get('access_token')
    if not access_token:
        return None
    datastore = cache.get(access_token)
    try:
        if datastore is not None:
            # Delete the cache entry now, so that if the refresh fails we
            # don't cache the probably invalid datastore.
            del cache[access_token]
            if refresh:
                datastore.load_deltas()
        else:
            client = DropboxClient(access_token)
            manager = DatastoreManager(client)
            datastore = manager.open_default_datastore()
            if len(cache) >= 32:
                to_delete = next(iter(cache))
                del cache[to_delete]
    except (ErrorResponse, DatastoreError):
        app.logger.exception('An exception occurred opening a datastore')
        return None
    cache[access_token] = datastore
    return datastore


# Dropbox auth routes and helper.  Same as ../flask_app/.

@app.route('/dropbox-auth-finish')
def dropbox_auth_finish():
    try:
        access_token, user_id, url_state = get_auth_flow().finish(request.args)
    except DropboxOAuth2Flow.BadRequestException as e:
        abort(400)
    except DropboxOAuth2Flow.BadStateException as e:
        abort(400)
    except DropboxOAuth2Flow.CsrfException as e:
        abort(403)
    except DropboxOAuth2Flow.NotApprovedException as e:
        return redirect(url_for('home'))
    except DropboxOAuth2Flow.ProviderException as e:
        app.logger.exception('Auth error' + e)
        abort(403)
    session['access_token'] = access_token
    return redirect(url_for('home'))


@app.route('/dropbox-auth-start')
def dropbox_auth_start():
    return redirect(get_auth_flow().start())


@app.route('/dropbox-logout')
def dropbox_logout():
    if 'access_token' in session:
        del session['access_token']
    return redirect(url_for('home'))


def get_auth_flow():
    redirect_uri = url_for('dropbox_auth_finish', _external=True)
    return DropboxOAuth2Flow(DROPBOX_APP_KEY, DROPBOX_APP_SECRET, redirect_uri,
                                       session, 'dropbox-auth-csrf-token')


# Main boilerplate.

def main():
    app.run(threaded=True)


if __name__ == '__main__':
    main()
