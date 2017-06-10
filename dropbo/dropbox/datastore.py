"""
Datastores are an easy way to keep an app's per-user data -- like
settings, bookmarks, or game state -- in sync across multiple devices
and operating systems.  Datastores are simple embedded databases,
which are synced to Dropbox.

This reference details the full set of classes needed when working
with datastores.  You can also read the Datastore API tutorial for a
detailed example of how to use them.

Unlike the client-side datastore APIs (for e.g. iOS, Android and
JavaScript), the Python datastore API does not implement automatic
conflict resolution.  Instead, if commit() fails, you must start over.
You can use the transaction() method for this, which allows you to
retry the transaction several times before giving up.

The Python API is not thread-safe.  If you want to use the same
Datastore object from multiple threads you should manage your own
locking.  The exception is the :class:`DatastoreManager` class; all
its methods are thread-safe.  Also, static methods are thread-safe.
"""

__all__ = ['DatastoreError', 'DatastoreNotFoundError', 'DatastoreConflictError',
           'DatastorePermissionError',
           'DatastoreManager', 'DatastoreInfo', 'Datastore', 'Table', 'Record',
           'Date', 'Bytes', 'List',
           ]

import array
import base64
import collections
import datetime
import hashlib
import json
import math
import re
import sys
import time
import uuid

# The port to Python 3 is not yet finished.
PY3 = sys.version_info[0] == 3

# Polyfill a few things for Bytes().
if PY3:  # pragma: no cover
    buffer = memoryview
    basestring = str
    long = int
else:
    bytearray = bytes

# Internal values for roles, used by the HTTP protocol.
ROLE_OWNER = 3000
ROLE_EDITOR = 2000
ROLE_VIEWER = 1000
ROLE_NONE = 0


def _dbase64_encode(b):
    """Internal helper to encode bytes using our base64 variant.

    This is like urlsafe base64 encode but strips the trailing '='
    padding.  Also, it returns a string, not a bytes object.
    """
    bb = base64.urlsafe_b64encode(b)
    ss = str(bb.decode('ascii'))
    s = ss.rstrip('=')  # Remove padding.
    return s


def _dbase64_decode(s):
    """Internal helper to decode bytes using our base64 variant.

    This is the inverse of _dbase64_encode(), taking a string,
    returning bytes.
    """
    ss = s + '=' * (4 - len(s) % 4)  # Add padding back.
    bb = ss.encode('ascii')
    b = base64.urlsafe_b64decode(bb)
    return b


def _generate_shareable_dsid():
    """Internal helper to generate a random shareable (dsid, key) pair."""
    # Start with 32 random bytes so the encoded key will be at least 32 characters in length.
    bkey = uuid.uuid4().bytes + uuid.uuid4().bytes
    key = _dbase64_encode(bkey)
    # Use the sha256 of the *encoded* key.
    keyhash = hashlib.sha256(key.encode('ascii')).digest()
    dsid = '.' + _dbase64_encode(keyhash)
    return dsid, key

class DatastoreError(Exception):
    """Exception raised for datastore-specific error conditions.

    This is the base class for more specific exception classes.
    """

    _resp__doc__ = """
        The JSON dict that was returned by the server.
        """

    def __init__(self, message, resp=None):
        super(DatastoreError, self).__init__(message)
        self.resp = resp


class DatastoreNotFoundError(DatastoreError):
    """Exception raised when attempting to open a non-existent datastore.

    Derives from :class:`DatastoreError`.
    """


class DatastoreConflictError(DatastoreError):
    """Exception raised when the server reports a conflict.

    Derives from :class:`DatastoreError`.
    """


class DatastorePermissionError(DatastoreError):
    """Exception raised when the server denies access.

    Derives from :class:`DatastoreError`.
    """


class _DatastoreOperations(object):
    """Low-level datastore operations.

    The methods here map 1:1 to endpoints in the HTTP API.

    Also, the parameter names exactly match the HTTP protocol, and the
    return value is the JSON dict returned by the request.

    The exception is create_datastore(), which takes no parameters and
    adds the generated datastore ID to the JSON dict.

    Exceptions that may be raised:

    - :class:`dropbox.rest.ErrorResponse` if the server returned an
      error
    - :class:`dropbox.rest.HTTPSocketError` if there was a
      network problem
    - :class:`DatastoreNotFoundError` if a specified datastore
      does not exist
    - :class:`DatastoreConflictError` if the server reports a write
      conflict
    - :class:`DatastoreError` if an unanticipated JSON response is
      received
    """

    def __init__(self, client):
        self._client = client

    def _check_access_errors(self, resp):
        if 'access_denied' in resp:
            raise DatastorePermissionError(resp['access_denied'], resp)
        if 'notfound' in resp:
            raise DatastoreNotFoundError(resp['notfound'], resp)
        return resp

    def _check_rev(self, resp):
        resp = self._check_access_errors(resp)
        if 'rev' not in resp:
            raise DatastoreError('rev missing from response: %r' % (resp,), resp)
        return resp

    def _check_handle(self, resp):
        resp = self._check_rev(resp)
        if 'handle' not in resp:
            raise DatastoreError('handle missing from response: %r' % (resp,), resp)
        return resp

    def _check_ok(self, resp):
        resp = self._check_access_errors(resp)
        if 'ok' not in resp:
            raise DatastoreError('ok missing from response: %r' % (resp,), resp)
        return resp

    def _check_conflict(self, resp):
        if 'conflict' in resp:
            raise DatastoreConflictError(resp['conflict'], resp)
        resp = self._check_rev(resp)
        return resp

    def _check_list_datastores(self, resp):
        if 'datastores' not in resp or 'token' not in resp:
            raise DatastoreError('token or datastores missing from response: %r' % (resp,),
                                 resp)
        return resp

    def _check_get_snapshot(self, resp):
        resp = self._check_rev(resp)
        if 'rows' not in resp:
            raise DatastoreError('rows missing from response: %r' % (resp,), resp)
        return resp

    def _check_await(self, resp):
        # Nothing to do here -- it may or may not have keys 'list_datastores' and 'get_deltas'.
        return resp

    def _check_get_deltas(self, resp):
        resp = self._check_access_errors(resp)
        # If there are no new deltas the response is empty.
        if resp and 'deltas' not in resp:
            raise DatastoreError('deltas missing from response: %r' % (resp,), resp)
        return resp

    def get_datastore(self, dsid):
        url, params, headers = self._client.request('/datastores/get_datastore',
                                                    {'dsid': dsid}, method='GET')
        resp = self._client.rest_client.GET(url, headers)
        return self._check_handle(resp)

    def get_or_create_datastore(self, dsid):
        url, params, headers = self._client.request('/datastores/get_or_create_datastore',
                                                    {'dsid': dsid})
        resp = self._client.rest_client.POST(url, params, headers)
        return self._check_handle(resp)

    def create_datastore(self):
        # NOTE: This generates a dsid locally and adds it to the returned response.
        dsid, key = _generate_shareable_dsid()
        url, params, headers = self._client.request('/datastores/create_datastore',
                                                    {'dsid': dsid, 'key': key})
        resp = self._client.rest_client.POST(url, params, headers)
        resp = self._check_handle(resp)
        if 'dsid' not in resp:
            resp['dsid'] = dsid
        return resp

    def delete_datastore(self, handle):
        url, params, headers = self._client.request('/datastores/delete_datastore',
                                                    {'handle': handle})
        resp = self._client.rest_client.POST(url, params, headers)
        return self._check_ok(resp)

    def list_datastores(self):
        url, params, headers = self._client.request('/datastores/list_datastores', method='GET')
        resp = self._client.rest_client.GET(url, headers)
        return self._check_list_datastores(resp)

    def get_snapshot(self, handle):
        url, params, headers = self._client.request('/datastores/get_snapshot',
                                                    {'handle': handle}, method='GET')
        resp = self._client.rest_client.GET(url, headers)
        return self._check_get_snapshot(resp)

    def get_deltas(self, handle, rev):
        url, params, headers = self._client.request('/datastores/get_deltas',
                                                    {'handle': handle, 'rev': rev},
                                                    method='GET')
        resp = self._client.rest_client.GET(url, headers)
        return self._check_get_deltas(resp)

    def put_delta(self, handle, rev, changes, nonce=None):
        args = {'handle': handle,
                'rev': str(rev),
                'changes': json.dumps(changes),
                }
        if nonce:
            args['nonce'] = nonce
        url, params, headers = self._client.request('/datastores/put_delta', args)
        resp = self._client.rest_client.POST(url, params, headers)
        return self._check_conflict(resp)

    def await(self, token=None, cursors=None):
        params = {}
        if token:
            params['list_datastores'] = json.dumps({'token': token})
        if cursors:
            params['get_deltas'] = json.dumps({'cursors': cursors})
        url, params, headers = self._client.request('/datastores/await', params, method='POST')
        resp = self._client.rest_client.POST(url, params, headers)
        return self._check_await(resp)

    def get_client(self):
        return self._client

class DatastoreManager(object):
    """A manager for datastores.

    In order to work with datastores you must first create an instance
    of this class, passing its constructor a
    :class:`dropbox.client.DropboxClient` instance.

    The methods here let you open or create datastores and retrieve
    the list of datastores.

    This class has no state except for a reference to the
    :class:`dropbox.client.DropboxClient`, which itself is thread-safe;
    hence, all methods of this class are thread-safe.
    """

    DEFAULT_DATASTORE_ID = 'default'  #: The default datastore ID.
    _DEFAULT_DATASTORE_ID__doc__ = """
        The default datastore ID used by :meth:`open_default_datastore()`.
        """

    def __init__(self, client):
        """Construct a ``DatastoreManager`` using a :class:`dropbox.client.DropboxClient`."""
        self._dsops = _DatastoreOperations(client)

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self._dsops._client if self._dsops else None)

    def close(self):
        # This doesn't do anything to the _DatastoreOperations object.
        self._dsops = None

    def get_client(self):
        """Return the :class:`dropbox.client.DropboxClient` object used."""
        return self._dsops.get_client()

    def open_default_datastore(self):
        """Open the default datastore for this account, creating it if needed.

        This is a shorthand for :meth:`open_or_create_datastore`\(:const:`DEFAULT_DATASTORE_ID`).

        Returns
            A :class:`Datastore` instance.
        """
        return self.open_or_create_datastore(self.DEFAULT_DATASTORE_ID)

    def open_datastore(self, id):
        """Open an existing datastore given its ID (a string).

        Returns
            A :class:`Datastore` instance.
        """
        if not Datastore.is_valid_id(id):
            raise ValueError('Invalid datastore ID %r' % (id,))
        resp = self._dsops.get_datastore(id)
        return self._datastore_from_response(resp, id)

    def open_or_create_datastore(self, id):
        """Open a private datastore, creating it if it does not yet exist.

        The ID must not start with a dot.

        Returns
            A :class:`Datastore` instance.
        """
        if not Datastore.is_valid_id(id):
            raise ValueError('Invalid datastore ID %r' % (id,))
        if id.startswith('.'):
            raise ValueError('Datastore ID must not start with dot')
        resp = self._dsops.get_or_create_datastore(id)
        return self._datastore_from_response(resp, id)

    def create_datastore(self):
        """Create a new datastore with a randomly assigned ID.

        The assigned ID will start with a dot.

        Returns
            A :class:`Datastore` instance.
        """
        resp = self._dsops.create_datastore()
        return self._datastore_from_response(resp, resp['dsid'])

    def open_raw_datastore(self, id, handle, role=None):
        """Create a new :class:`Datastore` object without going to the server.

        You can use this to save a server roundtrip when opening a
        datastore given a :class:`DatastoreInfo` object returned by
        :meth:`list_datastores()`::

            def open_from_info(mgr, info):
                ds = mgr.open_raw_datastore(info.id, info.handle, info.role)
                ds.load_snapshot()
                return ds
        """
        if role is None:
            role = Datastore.OWNER  # Our best guess.
        else:
            if not isinstance(role, basestring):
                raise TypeError('Role must be a string: %r' % (role,))
            if role not in (Datastore.OWNER, Datastore.EDITOR, Datastore.VIEWER):
                raise ValueError('invalid role (%r)' % (role,))
            if not id.startswith('.') and role != Datastore.OWNER:
                raise ValueError('private datastore role must be owner: %r' % (role,))
        return Datastore(self, id=id, handle=handle, role=role)

    def delete_datastore(self, id):
        """Delete a datastore given its ID."""
        resp = self._dsops.get_datastore(id)
        self._dsops.delete_datastore(resp['handle'])

    def _datastore_from_response(self, resp, id):
        handle = resp['handle']
        rev = resp['rev']
        role = _make_role(resp.get('role'))
        ds = Datastore(self, id=id, handle=handle, role=role)
        if rev > 0:
            ds.load_snapshot()
        return ds

    def list_datastores(self):
        """List the existing datastores for this account.

        Returns
            A list of :class:`DatastoreInfo` objects.
        """
        resp = self._dsops.list_datastores()
        return [_make_dsinfo(item) for item in resp['datastores']]

    def await(self, token=None, datastores=None):
        """Wait until certain changes occur.

        This methods implements a flexible and efficient long-polling
        mechanism that can be used to be notified of changes to
        specific datastores and/or to the list of datastores itself
        (for the current account).

        Parameters
          token
            An optional token that represents a hash of the list of
            datastores, computed by the server.  If this parameter is
            present and non-empty, ``await()`` will return when the
            list of datastores has changed in a way that would cause a
            different token to be computed, such as when a datastore
            is created or deleted.  The token should be obtained from
            the previous ``await()`` call; as a special case, the
            value ``'.'`` forces the call to return immediately with a
            fresh token (as does any outdated token).

          datastores
            An optional list of :class:`Datastore` instances or dict
            mapping such instances to revision numbers.  The instances
            represents currently open datastores for which you are
            interested in receiving updates.  If this parameter is a
            list of instances, the revision to compare is retrieved
            from each instance using :meth:`Datastore.get_rev()`.  If
            this parameter is present and non-empty, ``await()`` will
            return whenever a new revision is available for any of
            those datastores.

        The call also returns after a certain amount of time passes
        without activity.  The timeout is controlled by the server; it
        is currently approximately one minute.

        Returns
          A ``(token, dsinfos, deltamap)`` tuple.  The items are as follows:

          token
            A new token, or the value of the ``token`` parameter if
            there are no changes to the list of datastores.  You
            should pass this to the next ``await()`` call.

          dsinfo
            The full list of :class:`DatastoreInfo` objects (as
            returned by :meth:`list_datastores()`) if there is a new
            token, otherwise ``None``.

          deltamap
            Either a mapping indicating which of the given datastores
            were changed, or ``None`` if there are no changes to
            datastores to report.  If it is a mapping, each key is a
            :meth:`Datastore`, and the corresponding value is either a
            non-empty list of deltas, or ``None`` if that datastore is
            deleted or is otherwise invalid.  Datastores that were
            not changed (and are still valid) will not be present.

        Unlike :meth:`Datastore.load_deltas()` and
        :meth:`Datastore.await_deltas()`, ``await()`` does not apply
        the deltas returned in ``deltamap`` to the respective
        datastores; that is the caller's responsibility.  For
        example::

            for ds, deltas in deltamap.items():
                if deltas is not None:
                    ds.apply_deltas(deltas)
                else:
                    # ds has been deleted
        """
        cursors = None
        if datastores is not None:
            cursors = {}
            if isinstance(datastores, collections.Mapping):
                for ds, rev in datastores.items():
                    cursors[ds._handle] = rev
            else:
                for ds in datastores:
                    cursors[ds._handle] = ds._rev
        resp = self._dsops.await(token=token, cursors=cursors)
        dsinfos = None
        deltamap = None
        if 'list_datastores' in resp:
            subresp = resp['list_datastores']
            token = subresp['token']
            dsinfos = [_make_dsinfo(item) for item in subresp['datastores']]
        if 'get_deltas' in resp:
            subresp = resp['get_deltas']
            rawmap = subresp['deltas']
            deltamap = {}
            for ds in datastores:
                if ds._handle in rawmap:
                    value = rawmap[ds._handle]
                    # If this assert triggers, the server sent us bogus data.
                    assert isinstance(value, dict), repr(value)
                    if 'deltas' in value:
                        deltamap[ds] = value['deltas']
                    elif 'notfound' in value:
                        # This datastore is invalid.
                        deltamap[ds] = None
                    # Else the server sent us a response we don't
                    # understand; ignore it.
        return token, dsinfos, deltamap

    @staticmethod
    def make_cursor_map(datastores, deltamap):
        """Utility to construct a ``datastores`` argument for :meth:`await()`.

        Parameters
          datastores
            A list of :class:`Datastore` objects.
          deltamap
            An data structure as returned by :meth:`await()` in its
            ``deltamap`` return value.  This may be None or it may be
            a dict mapping :class:`Datastore` objects to values that
            are either lists of deltas or ``None``.

        Returns
          A dict mapping :class:`Datastore` objects to revisions,
          suitable to pass as the ``datastores`` parameter to
          :meth:`await()`.  This will normally just map the datastores
          from the ``datastores`` parameter to their current revision;
          however, datastores that are deleted or invalid according to
          ``deltamap`` are excluded from the dict, and for datastores
          that have one or more deltas in ``deltamap``, the revision
          is set to one higher than the revision of the last delta.

        Using this function will reduce redundant server roundtrips in
        multi-threaded apps that call :meth:`await()` in a background
        thread and then pass the received deltas to the main thread
        through some kind of queue.
        """
        if deltamap is None:
            deltamap = {}
        cursor_map = {}
        for ds in datastores:
            if ds not in deltamap:
                cursor_map[ds] = ds._rev
            else:
                deltas = deltamap[ds]
                # If this is None, the datastore is known to be
                # invalid, and we do not put it in the map.
                if deltas is not None:
                    assert deltas, 'Unexpected empty list of deltas in deltamap'
                    cursor_map[ds] = deltas[-1]['rev'] + 1
        return cursor_map


DatastoreInfo = collections.namedtuple('DatastoreInfo', 'id handle rev title mtime effective_role')

# Dummy class for docstrings, see doco.py.
class _DatastoreInfo__doc__(object):
    """A read-only record of information about a :class:`Datastore`.

    Instances of this class are returned by
    :meth:`DatastoreManager.list_datastores()`.
    """
    _id__doc__ = """The datastore ID (a string)."""
    _handle__doc__ = """The datastore handle (a string)."""
    _rev__doc__ = """The datastore revision (an integer >= 0)."""
    _title__doc__ = """The datastore title (string or None)."""
    _mtime__doc__ = """The time of last modification (:class:`Date` or None)."""
    _effective_role__doc__ = """
        The current user's effective role (:const:`Datastore.OWNER`,
        :const:`Datastore.EDITOR` or :const:`Datastore.VIEWER`).
        """


def _make_dsinfo(item):
    title = mtime = None
    info = item.get('info')
    if info:
        title = info.get('title')
        raw_mtime = info.get('mtime')
        if raw_mtime is not None:
            mtime = Date.from_json(raw_mtime)
    dsid = item['dsid']
    role = _make_role(item.get('role'))
    assert role is not None, repr(role)
    return DatastoreInfo(id=dsid, handle=item['handle'], rev=item['rev'],
                         title=title, mtime=mtime, effective_role=role)


def _make_role(irole):
    if irole is None:
        return Datastore.OWNER  # Backward compatible default.
    if not isinstance(irole, (int, long)):
        raise TypeError('irole must be an integer: %r', irole)
    # Unknown roles are truncated down to the nearest known role.
    if irole >= ROLE_OWNER:
        return Datastore.OWNER
    if irole >= ROLE_EDITOR:
        return Datastore.EDITOR
    if irole >= ROLE_VIEWER:
        return Datastore.VIEWER
    return Datastore.NONE


def _parse_role(role, owner_ok=False):
    if role == Datastore.OWNER and owner_ok:
        return ROLE_OWNER
    if role == Datastore.EDITOR:
        return ROLE_EDITOR
    if role == Datastore.VIEWER:
        return ROLE_VIEWER
    if role == Datastore.NONE:
        return ROLE_NONE
    if not isinstance(role, basestring):
        raise TypeError('invalid role type: %r' % (role,))
    raise ValueError('invalid role: %r' % (role,))


_DBASE64_VALID_CHARS = '-_A-Za-z0-9'
_VALID_PRIVATE_DSID_RE = r'[a-z0-9_-]([a-z0-9._-]{0,62}[a-z0-9_-])?'
_VALID_SHAREABLE_DSID_RE = r'\.[%s]{1,63}' % _DBASE64_VALID_CHARS
_VALID_DSID_RE = r'\A(%s|%s)\Z' % (_VALID_PRIVATE_DSID_RE, _VALID_SHAREABLE_DSID_RE)


class Principal(object):
    """A principal used in the access control list (ACL).

    Currently the only valid principals are the predefined objects
    :const:`Datastore.TEAM` and :const:`Datastore.PUBLIC`.
    """

    def __init__(self, key):
        assert self.__class__ is not Principal, 'Cannot directly instantiate Principal'
        self._key = key

    @property
    def key(self):
        return self._key

    def __hash__(self):
        return hash(self._key)

    def __eq__(self, other):
        if not isinstance(other, Principal):
            return NotImplemented
        return self._key == other._key

    def __ne__(self, other):
        if not isinstance(other, Principal):
            return NotImplemented
        return self._key != other._key


class User(Principal):
    """A user is identified by a numeric user ID (uid).

    The uid may be either an integer or a string of digits.
    """

    def __init__(self, uid):
        if not isinstance(uid, (int, long, basestring)):
            raise TypeError('Invalid uid type: %r' % (uid,))
        if not str(uid).isdigit():
            raise ValueError('Invalid uid: %r' % (uid,))
        if str(int(uid)) != str(uid):
            raise ValueError('Leading zeros or sign not allowed in uid: %r' % (uid,))
        if int(uid) <= 0:
            raise ValueError('Zero or negative uid not allowed: %r' % (uid,))
        super(User, self).__init__('u%s' % uid)

    def __repr__(self):
        return 'User(%s)' % self._key[1:]


class TeamPrincipal(Principal):
    """:const:`Datastore.TEAM` is a special principal to set team permissions.

    Don't instantiate this class, use the predefined :const:`Datastore.TEAM` variable.
    """

    def __init__(self):
        super(TeamPrincipal, self).__init__('team')

    def __repr__(self):
        return 'TEAM'


class PublicPrincipal(Principal):
    """:const:`Datastore.PUBLIC` is a special principal to set public permissions.

    Don't instantiate this class, use the predefined :const:`Datastore.PUBLIC` variable.
    """

    def __init__(self):
        super(PublicPrincipal, self).__init__('public')

    def __repr__(self):
        return 'PUBLIC'


class Datastore(object):
    """An object representing a datastore.

    A datastore holds a set of tables identified by table IDs, each of
    which holds a set of records identified by record IDs.  A record
    holds a set of field values identified by field names.  The
    ``Datastore`` object keeps a snapshot of the current content (all
    tables, records and fields) in memory and supports simple queries.

    Changes to a datastore are made through methods on the
    :class:`Table` and :class:`Record` classes, as well as the
    :class:`List` class (which represents a composite field value).

    Changes are not immediately sent to the server.  Instead, the
    datastore keeps a list of changes in memory; these are sent to the
    server by the :meth:`commit()` method.  The :meth:`load_deltas()`
    method retrieves new changes from the server and incorporates them
    into the current snapshot.  Those changes that have not yet been
    sent to the server can be undone using the :meth:`rollback()`
    method.  Finally, the :meth:`transaction()` method combines the
    functionality of these into a more powerful operation that can
    retry sets of changes specified by a callback function.

    **Do not instantiate this class directly**.  Use the methods on
    :class:`DatastoreManager` instead.
    """

    DATASTORE_SIZE_LIMIT = 10 * 1024 * 1024  #: Datastore size limit placeholder for sphinx.
    _DATASTORE_SIZE_LIMIT__doc__ = """
        The maximum size in bytes of a datastore.
        """

    PENDING_CHANGES_SIZE_LIMIT = 2 * 1024 * 1024  #: Delta size limit placeholder for sphinx.
    _PENDING_CHANGES_SIZE_LIMIT__doc__ = """
        The maximum size in bytes of changes that can be queued up between calls to
        :meth:`commit()`.
        """

    RECORD_COUNT_LIMIT = 100000  #: Record count limit placeholder for sphinx.
    _RECORD_COUNT_LIMIT__doc__ = """
        The maximum number of records in a datastore.
        """

    BASE_DATASTORE_SIZE = 1000  #: Base datastore size placeholder for sphinx.
    _BASE_DATASTORE_SIZE__doc__ = """
        The size in bytes of a datastore before accounting for the size of its records.

        The overall size of a datastore is this value plus the size of all records.
        """

    BASE_DELTA_SIZE = 100  #: Base delta size placeholder for sphinx.
    _BASE_DELTA_SIZE__doc__ = """
        The size in bytes of a delta before accounting for the size of each change.

        The overall size of a delta is this value plus the size of each change.
        """

    BASE_CHANGE_SIZE = 100  #: Base change size placeholder for sphinx.
    _BASE_CHANGE_SIZE__doc__ = """
        The size in bytes of a change before including the size of its values.

        The overall size of a change is this value plus the size of the values in the change.
        """

    TEAM = TeamPrincipal()  #: Team placeholder for sphinx.
    _TEAM__doc__ = """
        The principal used to get or modify the team role for a datastore.
        """

    PUBLIC = PublicPrincipal()  #: Public placeholder for sphinx.
    _PUBLIC__doc__ = """
        The principal used to get or modify the public role for a datastore.
        """

    OWNER = 'owner'  #: Owner placeholder for sphinx.
    _OWNER__doc__ = """
        The role indicating ownership of a datastore.  Owners have
        full access and their role cannot be changed or removed.
        """

    EDITOR = 'editor'  #: Editor placeholder for sphinx.
    _EDITOR__doc__ = """
        The role indicating edit (i.e., read-write) access.  Editors
        can also modify the role for other principals (except owners).
        """

    VIEWER = 'viewer'  #: Viewer placeholder for sphinx.
    _VIEWER__doc__ = """
        The role indicating view (i.e. read-only) access.  Viewers
        cannot change any aspect of a datastore.
        """

    NONE = 'none'  #: Viewer placeholder for sphinx.
    _NONE__doc__ = """
        The role indicating no access at all.
        """

    def __init__(self, manager, id=None, handle=None, role=None):
        if role is not None:
            # Should've been caught earlier.
            assert isinstance(role, str), repr(role)
            assert role in (Datastore.OWNER, Datastore.EDITOR, Datastore.VIEWER), repr(role)
        self._manager = manager
        self._id = id
        self._handle = handle
        self._role = role
        self._rev = 0
        self._tables = {}
        self._changes = []
        self._record_count = 0
        self._size = self.BASE_DATASTORE_SIZE
        self._pending_changes_size = 0

    def __repr__(self):
        return 'Datastore(<rev=%d>, id=%r, handle=%r, role=%r)' % (self._rev, self._id,
                                                                   self._handle, self._role)

    def _check_edit_permission(self):
        if self.is_shareable() and self._role not in (Datastore.OWNER, Datastore.EDITOR):
            raise DatastorePermissionError('This datastore is read-only')

    def _check_shareable(self):
        if not self.is_shareable():
            raise DatastoreError('Access control is only supported for shareable datastores')

    def _check_principal(self, principal):
        if not isinstance(principal, Principal):
            raise TypeError('A Principal is expected')

    @staticmethod
    def is_valid_id(id):
        """A helper method to check for a valid datastore ID.

        There are actually two types of datastore IDs, which
        are called private IDs and shareable IDs.

        Private datastores are created with
        :meth:`DatastoreManager.open_default_datastore()` or
        :meth:`DatastoreManager.open_or_create_datastore()`,
        and the app has control over the name.
        Valid private datastore IDs are 1-64 characters long and
        may contain the following characters: ``a-z 0-9 . - _`` .
        However the first and last character cannot be dots.  Note
        that upper case is not allowed.

        Shareable datastores are created with
        :meth:`DatastoreManager.create_datastore()`; the
        name is a dot followed by a random-looking sequence of
        characters assigned by the SDK.  Valid shareable datastore IDs
        are a dot followed by 1-63 dbase64 characters (which are
        ``a-z A-Z 0-9 - _``).  Note that upper case *is* allowed.

        The :meth:`DatastoreManager.open_datastore()` and
        :meth:`DatastoreManager.open_raw_datastore()` methods
        can open either type of datastores.
        """
        return bool(re.match(_VALID_DSID_RE, id))

    @staticmethod
    def is_valid_shareable_id(id):
        """A helper method to check for a valid shareable datastore ID.

        This is a valid datastore ID starting with a '.'.
        """
        return Datastore.is_valid_id(id) and id.startswith('.')

    def get_id(self):
        """Return the ID of this datastore (a string)."""
        return self._id

    def is_shareable(self):
        """Return whether this is a shareable datastore."""
        return self._id.startswith('.')

    def is_writable(self):
        """Return whether this datastore is writable.

        Always true for private datastores.
        False iff role==:const:`VIEWER` for shareable datastores.
        """
        return self._role != Datastore.VIEWER

    def get_handle(self):
        """Return the handle of this datastore (a string)."""
        return self._handle

    def get_rev(self):
        """Return the current revision of this datastore (an integer >= 0)."""
        return self._rev

    def get_manager(self):
        """Return the :class:`DatastoreManager` to which this datastore belongs."""
        return self._manager

    def get_mtime(self):
        """Return time this datastore was last modified, if known.

        This value is automatically set to the current time by
        :meth:`commit()`.

        Returns
          A :class:`Date` or None.
        """
        return self._get_info_field('mtime')

    def get_title(self):
        """Return the title of this datastore (a string or None).

        The title is primarily useful for apps that use shareable
        datastores to represent documents created by the user.  Using
        :meth:`set_title()` the title can be set to a string chosen by
        the user, and :meth:`DatastoreManager.list_datastores()` will
        return the titles (see :class:`DatastoreInfo`).  The app can
        then show the user a list of documents containing the title
        and time of last modification for each document without
        needing to open all datastores.
        """
        return self._get_info_field('title')

    def set_title(self, title):
        """Set the title of this datastore (a string or None).

        Since this operation is implemented by updating a reserved
        table, you must call :meth:`commit()` to send this change to
        the server.
        """
        if title is not None and not isinstance(title, basestring):
            raise TypeError('Title must be a string, not %s' % type(title).__name__)
        self._set_info_field('title', title)

    def _set_mtime(self):
        now = time.time()
        mtime = Date(now)
        self._set_info_field('mtime', mtime)

    def _get_info_field(self, field):
        info_table = self.get_table(':info')
        info_record = info_table.get('info')
        if info_record is None:
            return None
        return info_record.get(field)

    def _set_info_field(self, field, value):
        info_table = self.get_table(':info')
        info_record = info_table.get_or_insert('info')
        info_record.set(field, value)

    def get_record_count(self):
        """Return the number of records in this datastore."""
        return self._record_count

    def get_size(self):
        """Return the size in bytes of this datastore.

        The overall size of a datastore is calculated by summing the
        size of all records, plus the base size of an empty datastore itself.
        """
        return self._size

    def get_pending_changes_size(self):
        """Return the size in bytes of changes made since the last :meth:`commit()`.

        If there are any pending changes, the total size is given by summing the size
        of those changes and :const:`BASE_DELTA_SIZE`. If there are no pending
        changes, the total size is zero.
        """
        if self._changes:
            return Datastore.BASE_DELTA_SIZE + self._pending_changes_size
        else:
            return 0

    def _add_pending_change(self, change):
        self._changes.append(change)
        self._pending_changes_size += change.size()

    def get_effective_role(self):
        """Return the effective role for the current user.

        This can return :const:`OWNER`, :const:`EDITOR` or
        :const:`VIEWER`.

        For a private datastore this always returns :const:`OWNER`.
        """
        if self.is_shareable():
            return self._role
        else:
            return Datastore.OWNER

    def list_roles(self):
        """Return the full ACL, as a dict mapping principals to roles.

        This is only supported for shareable datastores.
        """
        self._check_shareable()
        acl_table = self.get_table(':acl')
        acl = {}
        for rec in acl_table.query():
            id = rec.get_id()
            if id == 'team':
                principal = Datastore.TEAM
            elif id == 'public':
                principal = Datastore.PUBLIC
            elif id.startswith('u') and id[1:].isdigit():
                principal = User(id[1:])
            else:
                continue  # pragma: nocover.
            acl[principal] = _make_role(rec.get('role'))
        return acl

    def get_role(self, principal):
        """Return the role for a principal.

        This can return :const:`OWNER`, :const:`EDITOR`,
        :const:`VIEWER`, or ``None``.

        The principal must be :const:`TEAM` or :const:`PUBLIC`.

        This is only supported for shareable datastores.

        This method only returns the role explicitly set for the given
        principal in the ACL; it is equivalent to
        ``ds.list_roles().get(principal)``.  The effective role for a
        principal may be different; it is affected by the full ACL as
        well as by team membership and ownership.

        To get the effective role for the current user, use
        :meth:`get_effective_role()`.
        """
        self._check_shareable()
        self._check_principal(principal)
        acl_table = self.get_table(':acl')
        rec = acl_table.get(principal.key)
        if rec is None:
            return Datastore.NONE
        else:
            return _make_role(rec.get('role'))

    def set_role(self, principal, role):
        """Set a principal's role.

        The principal must be :const:`TEAM` or :const:`PUBLIC`.
        The role must be :const:`EDITOR` or :const:`VIEWER`.

        If the principal already has a role it is updated.

        This is only supported for writable, shareable datastores.
        """
        if role == Datastore.NONE:
            return self.delete_role(principal)
        self._check_shareable()
        self._check_principal(principal)
        irole = _parse_role(role, owner_ok=False)
        acl_table = self.get_table(':acl')
        rec = acl_table.get(principal.key)
        if rec is None:
            acl_table.get_or_insert(principal.key, role=irole)
        else:
            rec.update(role=irole)

    def delete_role(self, principal):
        """Delete a principal's role.

        The principal must be :const:`TEAM` or :const:`PUBLIC`.

        The principal may but need not have a role.

        This is only supported for writable, shareable datastores.
        """
        self._check_shareable()
        self._check_principal(principal)
        acl_table = self.get_table(':acl')
        rec = acl_table.get(principal.key)
        if rec is not None:
            rec.delete_record()

    def load_snapshot(self):
        """Load the datastore with a snapshot retrieved from the server.

        All previously loaded content of the datastore is discarded,
        including pending changes.

        This is automatically called by most of the ``open_*()``
        methods, so there is normally no reason to call this.
        """
        resp = self._manager._dsops.get_snapshot(self._handle)
        rev = resp['rev']
        snapshot = resp['rows']
        self.apply_snapshot(rev, snapshot)

    def apply_snapshot(self, rev, snapshot):
        """Restore the datastore from a revision and a snapshot.

        All previously loaded content of the ``Datastore`` object is
        discarded, including pending changes.

        Normally this method is called internally by
        :meth:`load_snapshot()`.  It may also be called with a
        revision and snapshot obtained previously from
        :meth:`get_rev()` and :meth:`get_snapshot()`.
        """
        self._rev = 0
        self._tables = {}
        self._changes = []
        for row in snapshot:
            tid = row['tid']
            recordid = row['rowid']
            data = dict((field, _value_from_json(v)) for field, v in row['data'].items())
            table = self.get_table(tid)
            table._update_record_fields(recordid, data, _compute_record_size_for_fields(data))
        self._rev = rev

    def get_snapshot(self):
        """Return a snapshot of the datastore.

        A snapshot is a list of dicts with keys ``'tid'``,
        ``'rowid'``, and ``'data'``, where ``'tid'`` maps to the table
        ID, ``'rowid'`` maps to a record ID, and ``'data'`` maps to a
        JSON-encoded record, i.e. a dict mapping field names to
        JSON-encoded values.

        Together with the revision (which you can obtain from
        :meth:`get_rev()`) this comprises the mutable state of a
        datastore.  You may restore a ``Datastore`` object to a given
        state using :meth:`apply_snapshot()`.
        """
        snapshot = []
        for table_id, table in self._tables.items():
            for record_id, fields in table._records.items():
                data = {}
                for field, value in fields.items():
                    data[field] = _value_to_json(value)
                snapshot.append({'tid': table_id, 'rowid': record_id, 'data': data})
        return snapshot

    def await_deltas(self):
        """Wait for and incorporate changes to this datastore.

        It is an error to call this method if the datastore has
        pending changes.

        Returns
            A dict mapping table IDs to sets of records,
            see :meth:`apply_deltas()`.
        """
        if self._changes:
            raise DatastoreError('Cannot call await_deltas() with pending changes')
        resp = self._manager._dsops.await(cursors={self._handle: self._rev})
        if 'get_deltas' not in resp:
            return {}
        subresp = resp['get_deltas']
        if self._handle not in subresp['deltas']:
            return {}
        myresp = subresp['deltas'][self._handle]
        myresp = self._manager._dsops._check_access_errors(myresp)
        deltas = myresp.get('deltas')
        return self.apply_deltas(deltas)

    def load_deltas(self):
        """Load new changes retrieved from the server into the datastore.

        All previously loaded content is preserved, unless explicitly
        deleted or modified by one of the loaded changes.

        It is an error to call this method if the datastore has
        pending changes.

        Calling ``ds.load_deltas()`` is equivalent to::

            deltas = ds.fetch_deltas()
            ds.apply_deltas(deltas)

        Returns
            A dict mapping table IDs to sets of records,
            see :meth:`apply_deltas()`.
        """
        if self._changes:
            raise DatastoreError('Cannot call load_deltas() with pending changes')
        deltas = self.fetch_deltas()
        return self.apply_deltas(deltas)

    def fetch_deltas(self):
        """Retrieve new changes from the server without applying them.

        This is one of the building blocks of :meth:`load_deltas()`;
        you probably want to use that instead.

        Returns
            A list of deltas suitable to be passed directly to
            :meth:`apply_deltas()`.
        """
        resp = self._manager._dsops.get_deltas(self._handle, self._rev)
        return resp.get('deltas')

    def apply_deltas(self, deltas):
        """Apply deltas retrieved by some other means.

        It is an error to call this method if the datastore has
        pending changes.

        Normally this method is called internally by
        :meth:`await_deltas()` or :meth:`load_deltas()`.

        The deltas should be received from the server.  Under certain
        conditions (e.g. when :meth:`DatastoreManager.await()` is
        called in a background thread) it is possible that the server
        sends a delta that has already been applied locally.  Such
        deltas are silently ignored.

        Returns
            A dict mapping table IDs to sets of records,
            indicating the records that were inserted, updated or deleted
            by the loaded deltas.
        """
        if self._changes:
            raise DatastoreError('Cannot call apply_deltas() with pending changes')
        if deltas is None:
            return {}
        raw_changed_records = set()  # Set of (tid, recordid) tuples.
        for delta in deltas:
            rev = delta['rev']
            changes = delta['changes']
            if rev  < self._rev:
                continue  # We've already seen this revision, or it is ours.
            if rev != self._rev:
                # Either the server sent us bad data or our state is mixed up.
                raise DatastoreError('Revision out of sequence (expected %d, actual %d)' %
                                     (self._rev, rev))
            for c in changes:
               ch = _Change.from_json(c)
               tid, recordid = self._apply_change(ch)
               raw_changed_records.add((tid, recordid))
            self._rev = rev + 1
        changed_records = {}  # Map of tid to set of Record objects.
        for tid, recordid in raw_changed_records:
            record = Record(self._tables[tid], recordid)
            if tid in changed_records:
                changed_records[tid].add(record)
            else:
                changed_records[tid] = set([record])
        return changed_records

    def get_table(self, tid):
        """Get a :class:`Table` object with the given table ID."""
        t = self._tables.get(tid)
        if t is None:
            if not Table.is_valid_id(tid):
                raise ValueError('Invalid table ID %r' % (tid,))
            t = Table(self, tid)
            self._tables[tid] = t
        return t

    def list_table_ids(self):
        """List the non-empty tables for this datastore.

        Returns
            A set of strings table IDs (strings).
        """
        tids = set()
        for tid, table in self._tables.items():
            if table._records:
                tids.add(tid)
        return tids

    def rollback(self):
        """Discard all pending changes since the last successful :meth:`commit()`."""
        while self._changes:
            ch = self._changes.pop()
            inv = ch.invert()
            self._apply_change(inv)

    def commit(self):
        """Attempt to commit all pending changes.

        Pending changes are all mutations to a datastore made through
        :meth:`Table.insert()`, :meth:`Record.set()` and similar
        methods (inluding mutating :class:`List` methods).

        To upload pending changes to the server you must use
        :meth:`commit()`, or :meth:`transaction()`, which calls it.

        This method raises :class:`DatastoreConflictError` when the
        server detects a conflict and refuses to accept the changes.
        The proper response to this exception is to call
        :meth:`rollback()`, then :meth:`load_deltas()`, and then retry
        the transaction from the top, or give up and report an error
        to the user.  (The :meth:`transaction()` method implements
        this higher-level control flow.)

        If there are any changes, this method adds a change that
        updates the datastore's mtime.  If there are no changes, this
        method is a no-op (and no empty delta will be sent to the
        server).
        """
        self._check_edit_permission()
        if not self._changes:
            return
        self._set_mtime()
        changes = [ch.to_json() for ch in self._changes]
        nonce = _new_uuid()
        resp = self._manager._dsops.put_delta(self._handle, self._rev, changes, nonce)
        self._rev = resp['rev']
        self._changes = []

    def transaction(self, callback, *args, **kwds):
        """transaction(callback, *args, max_tries=1)

        Call a callback function and commit changes, with retries.

        When multiple clients try to update a datastore concurrently,
        it is possible for :meth:`commit()` to raise
        :class:`DatastoreConflictError`, indicating a conflict.  This
        function handles the details of handling such failures and
        retrying the updates.  You pass it a callback function which
        will be called repeatedly until :meth:`commit()` succeeds, or
        the maximum number of tries is reached.

        The keyword-only parameter ``max_tries`` specifies how many
        times the callback is called before giving up.  The default is
        1, i.e. call it only once; the recommended value is 4.

        Generally, if you plan to modify a datastore, you should do
        all your reads and writes in a transaction.  On entry, there
        should be no pending changes.

        Example::

            def do_stuff(record_id):
                record = tasks_table.get(record_id)
                user_count = record.get('user_count')
                record.update(user_count=user_count+1)

            datastore.transaction(do_stuff, some_record_id, max_tries=4)

        Extra positional arguments are passed on to the callback
        function.  On success, the return value of the callback is
        returned.

        When a commit attempt fails, uncommitted changes are rolled
        back using :meth:`rollback()`, and new changes are retrieved
        from the server and loaded into the datastore using
        :meth:`load_deltas()`.  This is done before checking whether
        we are out of tries.

        When giving up, :meth:`DatastoreError` is raised.

        When any other exception occurs (either in the callback or in
        the commit), uncommitted changes are rolled back and the last
        exception is re-raised.
        """
        # Hack: max_tries is a keyword-only parameter.
        max_tries = kwds.pop('max_tries', 1)
        if kwds:
            raise TypeError('Unexpected kwargs %r' % (kwds,))
        if max_tries < 1:
            raise ValueError('max_tries must be >= 1')
        # Note that catching BaseException is generally not advised.
        if self._changes:
            raise DatastoreError('There should be no pending changes')
        for _ in range(max_tries):
            try:
                rv = callback(*args)
            except Exception:
                # The callback failed; give up completely.
                self.rollback()
                raise
            try:
                self.commit()
            except DatastoreConflictError:
                # It's a conflict; update content and maybe try again.
                self.rollback()
                # If loading deltas fails, that's too bad.
                self.load_deltas()
            except Exception:
                # Some other error; give up completely.
                self.rollback()
                raise
            else:
                # Success!
                return rv
        # We ran out of tries.  But we've loaded new deltas.
        if max_tries == 1:
            raise DatastoreError('Failed to commit; set max_tries to a value > 1 to retry')
        else:
            raise DatastoreError('Failed to commit %d times in a row' % (max_tries,))

    # NOTE: The asserts below can only fire if the server sends bogus data.

    def _apply_change(self, change):
        op = change.op
        tid = change.tid
        recordid = change.recordid
        data = change.data
        table = self.get_table(tid)
        if op == INSERT:
            assert recordid not in table._records, repr((tid, recordid))
            table._update_record_fields(recordid, data, _compute_record_size_for_fields(data))
        elif op == DELETE:
            old_fields = table._records.get(recordid)
            table._update_record_fields(recordid, None,
                                        -_compute_record_size_for_fields(old_fields))
            change.undo = dict(old_fields)
        elif op == UPDATE:
            fields = dict(table._records[recordid])
            undo = {}
            old_size, new_size = 0, 0
            for field, val in data.items():
                old_value = fields.get(field)
                undo[field] = old_value
                if old_value is not None:
                    old_size += _compute_field_size(old_value)
                assert _is_op(val), repr(val)
                op = val[0]
                if op == ValuePut:
                    fields[field] = val[1]
                    new_size += _compute_field_size(val[1])
                elif op == ValueDelete:
                    # Silently ignore deletions for non-existing fields.
                    if field in data:
                        del fields[field]
                elif _is_listop(val):
                    new_list = self._apply_listop(fields.get(field), val)
                    fields[field] = new_list
                    new_size += _compute_field_size(new_list)
                else:
                    assert False, repr((field, val))  # pragma: no cover
            table._update_record_fields(recordid, fields, new_size - old_size)
            change.undo = undo
        else:
            assert False, repr(change)  # pragma: no cover
        return tid, recordid

    def _apply_listop(self, oldval, val):
        op = val[0]
        if op == ListCreate:
            assert oldval is None or oldval == (), repr(oldval)
            return ()
        assert isinstance(oldval, tuple), repr(oldval)
        if op == ListPut:
            index, newval = val[1:]
            return oldval[:index] + (newval,) + oldval[index+1:]
        if op == ListInsert:
            index, newval = val[1:]
            return oldval[:index] + (newval,) + oldval[index:]
        if op == ListDelete:
            index = val[1]
            return oldval[:index] + oldval[index+1:]
        if op == ListMove:
            return _list_move(oldval, *val[1:])
        assert False, repr(val)  # pragma: no cover

    def close(self):
        """Close the datastore.

        The datastore should not be used after this call.

        All pending changes are lost.
        """
        # Make essential stuff fail.
        self._manager = None
        self._changes = None


_VALID_ID_RE = r'([a-zA-Z0-9_\-/.+=]{1,64}|:[a-zA-Z0-9_\-/.+=]{1,63})\Z'


class Table(object):
    """An object representing a table in a datastore.

    You need a ``Table`` in order to query or modify the content of the datastore.

    **Do not instantiate this class directly**.  Use
    :meth:`Datastore.get_table()` instead.  Calls with the same ID will return
    the same object.
    """

    def __init__(self, datastore, tid):
        self._datastore = datastore
        self._tid = tid
        self._records = {}  # Map {recordid: fields}
        self._record_sizes = {} # Map {recordid: int size}

    def __repr__(self):
        return 'Table(<%s>, %r)' % (self._datastore._id, self._tid)

    @staticmethod
    def is_valid_id(id):
        """A helper method to check for a valid table ID.

        Valid table IDs are 1-64 characters long and may contain the
        following characters: ``a-z A-Z 0-9 _ - / . + =`` .  Reserved
        IDs start with a colon followed by 1-63 characters from that set.
        """
        return bool(re.match(_VALID_ID_RE, id))

    def get_id(self):
        """Return the ID of this table (a string)."""
        return self._tid

    def get_datastore(self):
        """Return the :class:`Datastore` to which this table belongs."""
        return self._datastore

    def get(self, recordid):
        """Return the record with the given record ID.

        If no such record exists, return None.
        """
        if recordid in self._records:
            return Record(self, recordid)
        if not Record.is_valid_id(recordid):
            raise ValueError('Invalid record ID %r' % (recordid,))
        return None

    def get_or_insert(self, recordid, **fields):
        """Return the record with the given record ID, or create it.

        If a record with the given record ID already exists, it is
        returned, and the keyword arguments are ignored.  If no such
        record exists, this inserts a record with the given record ID,
        setting its fields from the keyword arguments.
        """
        rec = self.get(recordid)
        if rec is not None:
            return rec
        return self._insert_with_id(recordid, fields)

    def insert(self, **fields):
        """Insert a new record into the table and return it.

        The new record's fields are set from the keyword arguments.
        A unique record ID is assigned automatically.
        """
        return self._insert_with_id(_new_uuid(), fields)

    def _insert_with_id(self, recordid, fields):
        self._datastore._check_edit_permission()
        value_size = 0
        for field, value in fields.items():
            if not Record.is_valid_field(field):
                raise ValueError('Invalid field name %r' % (field,))
            if value is None:
                raise TypeError('Cannot set field %r to None in insert' % (field,))
            value = _typecheck_value(value, field)
            value_size += _compute_field_size(value)
            fields[field] = value
        self._datastore._add_pending_change(_Change(INSERT, self._tid, recordid, dict(fields)))
        self._update_record_fields(recordid, fields, Record.BASE_RECORD_SIZE + value_size)
        return Record(self, recordid)

    def query(self, **kwds):
        """Query the records in the table.

        If called without arguments, this returns a set of all
        records in the table.

        If called with keyword arguments, each keyword argument
        specifies a required value for the corresponding field;
        only records that have the required field values for all
        keyword arguments are returned.

        The following example retrieves all records in the 'tasks'
        table that have a 'done' field whose type is ``bool`` and
        whose value is ``False``::

            to_do = tasks.query(done=False)

        For the purpose of queries, integers and floats are compared
        using the standard Python equality comparisons.

        Tip: specifying multiple keyword arguments implements a
        logical 'AND' operation; to implement a logical 'OR'
        operation, use the union of multiple queries.  For example::

            # Assume priority can be 1 (low), 2 (normal), 3 (high)
            urgent = tasks.query(done=False, priority=3)
            normal = tasks.query(done=False, priority=2)
            to_do = urgent | normal
        """
        filter = []
        for field, value in kwds.items():
            if not Record.is_valid_field(field):
                raise ValueError('Invalid field name %r' % (field,))
            value = _typecheck_value(value, field)
            filter.append((field, value))
        results = set()
        for recordid, fields in self._records.items():
            for field, value in filter:
                if field not in fields:
                    break
                rfv = fields[field]
                if rfv != value:
                    break
                # If the values match but the type don't, the filter
                # fails unless both types are numeric.
                trfv = type(rfv)
                tv = type(value)
                if trfv is not tv and not set((trfv, tv)) <= set((int, long, float)):
                    break
            else:
                results.add(Record(self, recordid))
        return results

    def _update_record_fields(self, recordid, fields, change_in_size):
        """Update the fields of the record, or delete the record if fields is None.

        This method updates the fields for the recordid and also updates its cached size in bytes
        and the cached size of the datastore.
        """
        curr_size = self._get_record_size(recordid)
        is_new_record = (curr_size == 0)
        curr_size += change_in_size
        assert curr_size >= 0, 'Invalid size %d for table %s, record %s' % (curr_size, self._tid,
                                                                            recordid)
        assert (self._datastore._size + change_in_size >=
                Datastore.BASE_DATASTORE_SIZE), 'Invalid datastore size %d' % (self._size,)
        if curr_size:
            self._record_sizes[recordid] = curr_size
            self._records[recordid] = fields
            if is_new_record:
                self._datastore._record_count += 1
        else:
            del self._record_sizes[recordid]
            del self._records[recordid]
            self._datastore._record_count -= 1
        self._datastore._size += change_in_size

    def _get_record_size(self, recordid):
        record_size = self._record_sizes.get(recordid)
        if not record_size:
            fields = self._records.get(recordid)
            # The values in this cache are maintained through _update_record_fields.  There is no
            # case in which a record with fields exists without having its size set properly in
            # the cache.
            assert fields is None, 'Record %r exists %r but has no cached size' % (recordid,
                                                                                   fields)
            record_size = 0
        return record_size


class Record(object):
    """An object representing a record in a table in a datastore.

    A record has a record ID and zero or more fields.  A record
    belongs to a specific table.  Two records are considered equal
    when they belong to the same table and have the same record ID;
    equal records by definition have the same fields.  Records are
    hashable.

    A field value can be an atomic type or a list of atomic types.

    Atomic types are ``bool``, integer (``int`` or ``long``), ``float``, string
    (``unicode`` or 8-bit ``str``; the latter must be a valid UTF-8 string), or an
    instance of the special classes :class:`Date` or :class:`Bytes`.  Note that ``None`` is
    not a valid field value.

    **Do not instantiate this class directly**.  Use
    :meth:`Table.get()`, :meth:`Table.insert()`,
    :meth:`Table.get_or_insert()` or :meth:`Table.query()` instead.
    """

    RECORD_SIZE_LIMIT = 100 * 1024  #: Record size limit placeholder for sphinx.
    _RECORD_SIZE_LIMIT__doc__ = """
        The maximum size in bytes of a record.
        """

    BASE_RECORD_SIZE = 100  #: Base record size placeholder for sphinx.
    _BASE_RECORD_SIZE__doc__ = """
        The size in bytes of a record before accounting for the sizes of its fields.

        The overall size of a record is this value plus the sum of the sizes of its fields.
        """

    BASE_FIELD_SIZE = 100  #: Base field size placeholder for sphinx.
    _BASE_FIELD_SIZE__doc__ = """
        The size in bytes of a field before accounting for the sizes of its values.

        The overall size of a field is this value plus:

        - For string and :class:`Bytes`: the length in bytes of the value.
        - For :class:`List`: the sum of the size of each list item, where each item's size
          is computed as the size of the item value plus :const:`List.BASE_ITEM_SIZE`.
        - For other atomic types: no additional contribution to the size of the field.
        """

    def __init__(self, table, recordid):
        self._table = table
        self._datastore = table._datastore
        self._recordid = recordid

    def __repr__(self):
        fields = self._table._records.get(self._recordid)
        if fields is None:
            return 'Record(<%s>, %r, <deleted>)' % (self._table._tid, self._recordid)
        else:
            return 'Record(<%s>, %r, %r)' % (self._table._tid, self._recordid, fields)

    def __eq__(self, other):
        if not isinstance(other, Record):
            return NotImplemented
        return self._table is other._table and self._recordid == other._recordid

    def __ne__(self, other):
        r = self.__eq__(other)
        if r is not NotImplemented:
            r = not r
        return r

    def __hash__(self):
        return hash((self._table._tid, self._recordid))

    @staticmethod
    def is_valid_id(id):
        """A helper method to check for a valid record ID.

        Valid record IDs are 1-64 characters long and may contain the
        following characters: ``a-z A-Z 0-9 _ - / . + =`` .  Reserved
        IDs start with a colon followed by 1-63 characters from that set.
        """
        return bool(re.match(_VALID_ID_RE, id))

    @staticmethod
    def is_valid_field(field):
        """A helper method to check for a valid field name.

        Valid field names are 1-64 characters long and may contain the
        following characters: ``a-z A-Z 0-9 _ - / . + =`` .  Reserved
        field names start with a colon followed by 1-63 characters
        from that set.
        """
        return bool(re.match(_VALID_ID_RE, field))

    def get_id(self):
        """Return the ID of this record (a string)."""
        return self._recordid

    def get_table(self):
        """Return the :class:`Table` to which this record belongs."""
        return self._table

    def get_size(self):
        """Return the size in bytes of this record.

        The overall size of a record is calculated by summing the
        size of all values in all fields, plus the base size of an empty
        record itself.  A deleted record has a size of zero.
        """
        return self._table._get_record_size(self._recordid)

    def get(self, field):
        """Return the value of a field in the record.

        If the record does not have a field by that name, return ``None``.

        If the field value is a list, this returns a :class:`List` object;
        mutating that object will modify the field's value in the record.
        """
        fields = self._table._records.get(self._recordid)
        if fields is None:
            v = None
        else:
            v = fields.get(field)
            if isinstance(v, tuple):
                v = List(self, field)
        # Skip field validation if we actually have a value.
        if v is None and not Record.is_valid_field(field):
            raise ValueError('Invalid field name %r' % (field,))
        return v

    def set(self, field, value):
        """Set the value of a field in the record.

        Setting the value to ``None`` deletes the field.
        """
        self.update(**{field: value})

    def delete(self, field):
        """Delete the value of a field in the record.

        If the field does not exist this is a no-op.
        """
        self.update(**{field: None})

    def get_fields(self):
        """Return a dict mapping all the fields in the record to their values.

        Modifying the dict will not affect the record in the datastore.

        To enforce this, list values are returned as tuples.
        """
        fields = self._table._records.get(self._recordid)
        if fields is None:
            return {}
        return dict(fields)

    def update(self, **kwds):
        """Set the value of multiple fields in the record.

        For each keyword argument, the field by that name is set to
        the corresponding value, except that if the value is ``None``, the
        field is deleted.
        """
        self._datastore._check_edit_permission()
        fields = self._table._records.get(self._recordid)
        if fields is None:
            raise DatastoreError('Cannot update a deleted record')
        fields = dict(fields)
        data = {}
        undo = {}
        old_size, new_size = 0, 0
        for field, value in kwds.items():
            if not Record.is_valid_field(field):
                raise ValueError('Invalid field name %r' % (field,))
            if value is None:
                old_value = fields.get(field)
                if old_value:
                    undo[field] = old_value
                    old_size += _compute_field_size(old_value)
                    del fields[field]
                    data[field] = [ValueDelete]
            else:
                old_value = fields.get(field)
                undo[field] = old_value
                old_size += _compute_field_size(old_value)
                value = _typecheck_value(value, field)
                fields[field] = value
                new_size += _compute_field_size(value)
                data[field] = [ValuePut, value]
        if data:
            change = _Change(UPDATE, self._table._tid, self._recordid, data=data, undo=undo)
            self._table._datastore._add_pending_change(change)
            self._table._update_record_fields(self._recordid, fields, new_size - old_size)

    def delete_record(self):
        """Delete the record from the table.

        If the record is already marked as deleted, this is a no-op.

        A record marked as deleted cannot be re-inserted, cannot be
        modified, and no longer has any fields.  To check for a
        deleted record, use :meth:`is_deleted()`.
        """
        self._datastore._check_edit_permission()
        fields = self._table._records.get(self._recordid)
        if fields is None:
            return
        change = _Change(DELETE, self._table._tid, self._recordid, data=None, undo=fields)
        self._table._datastore._add_pending_change(change)
        self._table._update_record_fields(self._recordid, None, -self.get_size())

    def get_or_create_list(self, field):
        """Get a list field, possibly setting it to an empty list.

        If the field exists, it must be a list.  If it does not exist,
        it is set to an empty list.  In either case, a :class:`List`
        object representing the field is returned.
        """
        fields = self._table._records.get(self._recordid)
        if fields is None:
            raise DatastoreError('Cannot update a deleted record')
        v = fields.get(field)
        if isinstance(v, tuple):
            return List(self, field)
        if v is not None:
            raise TypeError('Field %r already exists but is a %s instead of a list' %
                            (field, type(v).__name__))
        if not Record.is_valid_field(field):
            raise ValueError('Invalid field name %r' % (field,))
        self._datastore._check_edit_permission()
        # Produce a ListCreate op.
        data = {field: _make_list_create()}
        change = _Change(UPDATE, self._table._tid, self._recordid, data=data, undo={field: None})
        self._table._datastore._add_pending_change(change)
        fields = dict(fields)
        fields[field] = ()
        self._table._update_record_fields(self._recordid, fields, self.BASE_FIELD_SIZE)
        return List(self, field)

    def has(self, field):
        """Inquire whether the record has a given field.

        Return ``True`` if the field exists, ``False`` if not.
        """
        fields = self._table._records.get(self._recordid)
        found = fields is not None and field in fields
        if not found and not Record.is_valid_field(field):
            raise ValueError('Invalid field name %r' % (field,))
        return found

    def is_deleted(self):
        """Inquire whether the record is marked as deleted.

        Return ``True`` if the record has been deleted, ``False`` if not.
        """
        return self._recordid not in self._table._records


class Date(object):
    """A simple immutable object representing a timestamp.

    Datastores store timestamps as milliseconds since the Epoch
    (1/1/1970) in UTC.

    To store a timestamp, you must set a field to a ``Date``
    object; if a field value is a timestamp, getting the value will
    return a ``Date``.

    To construct a ``Date``, pass the constructor a POSIX
    timestamp as returned by ``time.time()`` (and many other standard
    Python APIs).

    You can convert a ``Date`` back to a POSIX timestamp by
    calling ``float()`` or ``int()`` on it.  These conversions take
    care of the conversion between seconds and milliseconds;
    milliseconds map to fractions when converting to/from ``float``,
    and are truncated when converting to ``int``.

    You can also convert between Date and naive (``tzinfo``-less) ``datetime``
    objects using a choice of UTC or local time, using
    :meth:`to_datetime_utc()`, :meth:`from_datetime_utc()`,
    :meth:`to_datetime_local()`, and :meth:`from_datetime_local()`.
    Note that ``datetime`` objects using an explicit ``tzinfo`` field are not
    supported; if you need to work with those you must convert to/from
    naive ``datetime`` objects yourself.
    """

    def __init__(self, timestamp=None):
        """Construct a ``Date`` from a timestamp.

        The timestamp is an integer or float specifying seconds since
        the epoch.  It defaults to the current time.
        """
        if timestamp is None:
            timestamp = time.time()
        else:
            if not isinstance(timestamp, (float, int, long)):
                raise TypeError('Timestamp must be a float or integer, not %s' %
                                type(timestamp).__name__)
        self._timestamp = int(timestamp*1000.0) / 1000.0

    def __repr__(self):
        dt = datetime.datetime.utcfromtimestamp(int(self._timestamp))
        ms = (self._timestamp * 1000) % 1000
        return 'Date<%s.%03d UTC>' % (str(dt), ms)

    def __float__(self):
        return self._timestamp

    def __int__(self):
        return int(self._timestamp)

    def __long__(self):
        return long(self._timestamp)

    def __eq__(self, other):
        if not isinstance(other, Date):
            return NotImplemented
        return self._timestamp == other._timestamp

    def __ne__(self, other):
        if not isinstance(other, Date):
            return NotImplemented
        return self._timestamp != other._timestamp

    def __lt__(self, other):
        if not isinstance(other, Date):
            return NotImplemented
        return self._timestamp < other._timestamp

    def __le__(self, other):
        if not isinstance(other, Date):
            return NotImplemented
        return self._timestamp <= other._timestamp

    def __gt__(self, other):
        if not isinstance(other, Date):
            return NotImplemented
        return self._timestamp > other._timestamp

    def __ge__(self, other):
        if not isinstance(other, Date):
            return NotImplemented
        return self._timestamp >= other._timestamp

    def to_datetime_utc(self):
        """Convert a ``Date`` to a ``datetime.datetime`` object in UTC.

        This sets the ``tzinfo`` field to ``None``.
        """
        return datetime.datetime.utcfromtimestamp(self._timestamp)

    @classmethod
    def from_datetime_utc(cls, dt):
        """Convert a ``datetime.datetime`` object in UTC to a ``Date``.

        The ``tzinfo`` field must be ``None``.
        """
        if dt.tzinfo is not None:
            raise TypeError('The argument datetime must not have a timezone')
        delta = dt - datetime.datetime.utcfromtimestamp(0)
        return cls(delta.days * 24*3600 + delta.seconds + delta.microseconds * 0.000001)

    def to_datetime_local(self):
        """Convert a ``Date`` to a ``datetime.datetime`` object in local time.

        This set the ``tzinfo`` field to ``None``.
        """
        return datetime.datetime.fromtimestamp(self._timestamp)

    @classmethod
    def from_datetime_local(cls, dt):
        """Convert a ``datetime.datetime`` object in UTC to a ``Date``.

        The ``tzinfo`` field must be ``None``.
        """
        if dt.tzinfo is not None:
            raise TypeError('The argument datetime must not have a timezone')
        # Keep the fraction separate because timetuple() doesn't store it.
        fraction = dt.microsecond * 0.000001
        return cls(time.mktime(dt.timetuple()) + fraction)

    # JSON encoding used by protocol.

    def to_json(self):
        return {TIMESTAMP: str(int(self._timestamp * 1000))}

    @classmethod
    def from_json(cls, j):
        # If this assert fires the server sent us bad data.
        assert (isinstance(j, dict) and
                list(j) == [TIMESTAMP] and
                isinstance(j[TIMESTAMP], basestring)), repr(j)
        timestamp = int(j[TIMESTAMP]) / 1000.0
        return cls(timestamp)


class Bytes(object):
    """A simple immutable object representing a binary string.

    Datastores transmit binary strings using a base64 encoding.

    Because Python 2 uses ambiguous representations of binary strings,
    you must wrap binary strings in this class in order to store them
    in a datastore.  8-bit strings not wrapped this way are assumed to
    represent text and must use the UTF-8 encoding.

    To construct a :class:`Bytes`, pass the constructor a ``str``
    instance, a ``buffer`` instance, or an ``array.array`` instance
    whose typecode indicate a one-byte-wide data type (i.e. ``'c'``, ``'b'``
    or ``'B'``).

    To convert a :class:`Bytes` to a raw byte string, call ``bytes()``
    on it.
    """

    def __init__(self, blob):
        """Construct a Bytes from an 8-bit string."""
        if not (isinstance(blob, (bytes, bytearray, buffer)) or
                isinstance(blob, array.array) and blob.typecode in ('c', 'b', 'B')):
            raise TypeError('Bytes must be a bytes-compatible type, not %s' %
                            type(blob).__name__)
        self._bytes = bytes(blob)  # Make a copy in case the argument is mutable.

    def __repr__(self):
        return 'Bytes(%r)' % self._bytes

    if PY3:  # pragma: no cover

        def __bytes__(self):
            return self._bytes

        def __str__(self):
            return repr(self)

    else:

        def __str__(self):
            return self._bytes

        def __unicode__(self):
            return repr(self)

    def __eq__(self, other):
        if isinstance(other, bytes):
            return self._bytes == other
        if isinstance(other, Bytes):
            return self._bytes == other._bytes
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, bytes):
            return self._bytes != other
        if isinstance(other, Bytes):
            return self._bytes != other._bytes
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, bytes):
            return self._bytes < other
        if isinstance(other, Bytes):
            return self._bytes < other._bytes
        return NotImplemented

    def __le__(self, other):
        if isinstance(other, bytes):
            return self._bytes <= other
        if isinstance(other, Bytes):
            return self._bytes <= other._bytes
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, bytes):
            return self._bytes > other
        if isinstance(other, Bytes):
            return self._bytes > other._bytes
        return NotImplemented

    def __ge__(self, other):
        if isinstance(other, bytes):
            return self._bytes >= other
        if isinstance(other, Bytes):
            return self._bytes >= other._bytes
        return NotImplemented

    def __len__(self):
        return len(self._bytes)

    # JSON encoding used by protocol.

    def to_json(self):
        s = _dbase64_encode(self._bytes)
        return {BLOB: s}

    @classmethod
    def from_json(cls, j):
        # If this assert fires the server sent us bad data.
        assert (isinstance(j, dict) and
                list(j) == [BLOB] and
                isinstance(j[BLOB], basestring)), repr(j)
        b = _dbase64_decode(j[BLOB])
        return cls(b)


class List(collections.MutableSequence):
    """A wrapper for a list value.

    When a field contains a list value, retrieving the field using
    :meth:`Record.get()` returns a ``List`` object.  This object
    behaves like a mutable sequence, but mutating it (e.g., replacing
    an item with a new value) will mutate the list value in the
    record.

    A ``List`` object knows the record and field to which it
    refers.  Multiple ``List`` objects may refer to the same record and
    field.

    ``List`` objects are compared by value (i.e., the sequence of
    items they contain, not the record and field to which they refer).
    They can also be compared to regular tuples and lists.

    Several methods available for regular lists are available for
    ``List`` objects, when in doubt, consult the documentation
    below.  Some methods unique to ``List`` objects also exist.

    Negative indices are supported in the usual fashion.

    **Do not instantiate this class directly**.  Use
    :meth:`Record.get()` or :meth:`Record.get_or_create_list()` instead.
    """

    BASE_ITEM_SIZE = 20  #: Base list item size placeholder for sphinx.
    _BASE_ITEM_SIZE__doc__ = """
        The size in bytes of a list item.

        The overall size of a list item is this value plus the size of the item value.
        """

    def __init__(self, record, field):
        self._table = record._table
        self._recordid = record._recordid
        self._field = field
        self._check()

    def __repr__(self):
        return 'List(<%s>, %r)' % (self._recordid, self._field)

    def __eq__(self, other):
        if not isinstance(other, (List, list, tuple)):
            return NotImplemented
        return tuple(self) == _typecheck_list(other, self._field)

    def __ne__(self, other):
        if not isinstance(other, (List, list, tuple)):
            return NotImplemented
        return tuple(self) != _typecheck_list(other, self._field)

    def __lt__(self, other):
        if not isinstance(other, (List, list, tuple)):
            return NotImplemented
        return tuple(self) < _typecheck_list(other, self._field)

    def __le__(self, other):
        if not isinstance(other, (List, list, tuple)):
            return NotImplemented
        return tuple(self) <= _typecheck_list(other, self._field)

    def __gt__(self, other):
        if not isinstance(other, (List, list, tuple)):
            return NotImplemented
        return tuple(self) > _typecheck_list(other, self._field)

    def __ge__(self, other):
        if not isinstance(other, (List, list, tuple)):
            return NotImplemented
        return tuple(self) >= _typecheck_list(other, self._field)

    def get_record(self):
        """Return the :class:`Record` to which this ``List`` refers."""
        return self._table.get(self._recordid)

    def get_field(self):
        """Return the field name (a string) to which this ``List`` refers."""
        return self._field

    def _check(self):
        fields = self._table._records.get(self._recordid)
        if fields is None:
            raise TypeError('Cannot use a List referring to a deleted record')
        v = fields.get(self._field)
        if not isinstance(v, tuple):
            raise TypeError('Cannot use a List referring to a non-list field')
        return v

    def __len__(self):
        v = self._check()
        return len(v)

    def __iter__(self):
        v = self._check()
        return iter(v)

    def __contains__(self, value):
        v = self._check()
        return value in v

    def __getitem__(self, index):
        v = self._check()
        return v[index]

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            raise TypeError('Cannot set List slices')
        value = _typecheck_atom(value, self.get_field(), True)
        v = self._check()
        if index < 0:
            index += len(v)
        if not 0 <= index < len(v):
            raise IndexError
        v = v[:index] + (value,) + v[index+1:]
        self._update(v, _make_list_put(index, value))

    def __delitem__(self, index):
        if isinstance(index, slice):
            raise TypeError('Cannot delete List slices')
        v = self._check()
        if index < 0:
            index += len(v)
        if not 0 <= index < len(v):
            raise IndexError
        v = v[:index] + v[index+1:]
        self._update(v, _make_list_delete(index))

    def insert(self, index, value):
        """Insert a value into the list at a given index."""
        value = _typecheck_atom(value, self.get_field(), True)
        v = self._check()
        n = len(v)
        if index < 0:
            index += n
            if index < 0:
                index = 0
        elif index > n:
            index = n
        v = v[:index] + (value,) + v[index:]
        self._update(v, _make_list_insert(index, value))

    def append(self, value):
        """Append a value to the end of the list."""
        value = _typecheck_atom(value, self.get_field(), True)
        v = self._check()
        index = len(v)
        v = v + (value,)
        self._update(v, _make_list_insert(index, value))

    def move(self, index, newindex):
        """Move the list item at ``index`` to position ``newindex``.

        This is most easily explained as follows: first delete the
        item at position ``index``; then re-insert it at position
        ``newindex``.
        """
        v = self._check()
        n = len(v)
        if index < 0:
            index += n
        if not 0 <= index < len(v):
            raise IndexError
        if newindex < 0:
            newindex += n
        if not 0 <= newindex < len(v):
            raise IndexError
        v = _list_move(v, index, newindex)
        self._update(v, _make_list_move(index, newindex))

    def _update(self, v, op):
        self._table._datastore._check_edit_permission()
        table = self._table
        recordid = self._recordid
        field = self._field
        fields = table._records[recordid]
        old_v = fields.get(field)
        change = _Change(UPDATE, table._tid, recordid,
                         data={field: op}, undo={field: old_v})
        table._datastore._add_pending_change(change)
        fields = dict(fields)
        fields[field] = v
        table._update_record_fields(recordid, fields,
                                    _compute_value_size(v) - _compute_value_size(old_v))


VALID_ATOM_TYPES = frozenset([
    int,
    bool,
    float,
    str,
    Date,
    Bytes,
    List,
    ] + ([bytes] if PY3 else [long, unicode]))


def _typecheck_value(value, field):
    if isinstance(value, (List, list, tuple)):
        return _typecheck_list(value, field)
    else:
        return _typecheck_atom(value, field)


def _typecheck_list(value, field):
    return tuple(_typecheck_atom(item, field, is_list=True)
                 for item in value)


def _typecheck_atom(value, field, is_list=False):
    if type(value) not in VALID_ATOM_TYPES:
        if is_list:
            format = 'Type %s is not an acceptable list item type (field %r)'
        else:
            format = 'Type %s is not an acceptable value type (field %r)'
        raise TypeError(format % (type(value).__name__, field))
    if isinstance(value, str) and not PY3:
        # Convert 8-bit strings to Unicode using UTF-8.
        # If this raises UnicodeDecodeError your data is not in UTF-8 format.
        value = value.decode('utf-8')
    return value


def _compute_record_size_for_fields(fields):
    """Compute the size in bytes of a record containing the given fields."""
    return Record.BASE_RECORD_SIZE + sum(map(_compute_field_size, fields.itervalues()))


def _compute_field_size(value):
    """Compute the size in bytes of a field with the given value.

    Returns 0 when field is None.
    """
    if value is None:
        return 0
    return Record.BASE_FIELD_SIZE + _compute_value_size(value)


def _compute_value_size(value):
    """Compute the size in bytes of the value.

    Sizes are computed as follows:
      String: length of the (utf-8) string.
      Bytes:  length in bytes.
      List:   sum of (:const:`List.LIST_VALUE_SIZE` + atom value) for each value in the list.
      Others: free
    """
    if isinstance(value, (List, list, tuple)):
        return _compute_list_size(value)
    else:
        return _compute_atom_size(value)


def _compute_list_size(value):
    return (len(value) * List.BASE_ITEM_SIZE) + sum(map(_compute_atom_size, value))


def _compute_atom_size(value):
    if value is None:
        return 0
    if isinstance(value, (int, long, bool, float, Date)):
        return 0
    if PY3:  # pragma: no cover
        if isinstance(value, str):
            value = value.encode('utf-8')
        if isinstance(value, bytes):
            return len(value)
    else:
        if isinstance(value, unicode):
            value = value.encode('utf-8')
        if isinstance(value, str):
            return len(value)
    if isinstance(value, Bytes):
        return len(value)
    assert False, 'Type %r is not a valid atom (value: %r)' % (type(value), value)


# Change ops.
INSERT, UPDATE, DELETE = 'I', 'U', 'D'

class _Change(object):

    REVERSED_OPS = {INSERT: DELETE, UPDATE: UPDATE, DELETE: INSERT}

    def __init__(self, op, tid, recordid, data=None, undo=None):
        assert op in (INSERT, UPDATE, DELETE), repr(op)
        assert isinstance(tid, basestring), repr(tid)
        assert isinstance(recordid, basestring), repr(recordid)
        if data is None:
            assert op == DELETE, repr(op)
        else:
            assert op != DELETE, repr(op)
            assert isinstance(data, dict), repr(data)
        if undo is not None:
            assert op != INSERT, repr(op)
            assert isinstance(undo, dict), repr(undo)
        self.op = op
        self.tid = tid
        self.recordid = recordid
        self.data = data
        self.undo = undo

    def __repr__(self):
        args = [self.op, self.tid, self.recordid]
        if self.data is not None or self.undo is not None:
            args.append(self.data)
            if self.undo is not None:
                args.append(self.undo)
        return '_Change(%s)' % (', '.join(map(repr, args)))

    def __eq__(self, other):
        if not isinstance(other, _Change):
            return NotImplemented
        return (self.op == other.op and
                self.tid == other.tid and
                self.recordid == other.recordid and
                self.data == other.data and
                self.undo == other.undo)

    def __ne__(self, other):
        eq = self.__eq__(other)
        if eq is not NotImplemented:
            eq = not eq
        return eq

    def without_undo(self):
        return _Change(self.op, self.tid, self.recordid, self.data)

    def size(self):
        change_size = Datastore.BASE_CHANGE_SIZE
        if self.op == INSERT:
            change_size += sum((Record.BASE_FIELD_SIZE + _compute_value_size(val))
                               for val in self.data.itervalues())
        elif self.op == UPDATE:
            for field_op in self.data.itervalues():
                change_size += Record.BASE_FIELD_SIZE
                op_value = _get_op_value(field_op)
                if op_value is not None:
                    change_size += _compute_value_size(op_value)
        return change_size

    def invert(self):
        if self.op == UPDATE:
            newdata = {}
            newundo = {}
            for name, op in self.data.items():
                assert _is_op(op), repr((name, op))
                if _is_listop(op):
                    newdata[name], newundo[name] = self._invert_listop(name, op)
                else:
                    # Before and after are from op's POV.
                    before = self.undo.get(name)
                    opid = op[0]
                    if opid == ValuePut:
                        after = op[1]
                        if before is None:
                            newdata[name] = [ValueDelete]
                            newundo[name] = after
                        else:
                            newdata[name] = [ValuePut, before]
                            newundo[name] = after
                    elif opid == ValueDelete:
                        newdata[name] = [ValuePut, before]
                        newundo[name] = None
                    else:
                        assert False, repr((name, op))  # pragma: no cover
            return _Change(UPDATE, self.tid, self.recordid, newdata, newundo)
        else:
            return _Change(self.REVERSED_OPS[self.op], self.tid, self.recordid,
                           data=self.undo, undo=self.data)

    def _invert_listop(self, name, op):
        assert _is_listop(op), repr(op)
        # Before and after are from op's POV.
        before = self.undo[name]
        opid = op[0]
        if opid == ListCreate:
            after = ()
            invop = [ValueDelete]
            return invop, after
        index = op[1]
        assert isinstance(before, tuple), repr((name, before))
        if opid == ListPut:
            assert 0 <= index < len(before), repr((name, index, len(before)))
            opvalue = op[2]
            after = before[:index] + (opvalue,) + before[index+1:]
            invop = _make_list_put(index, before[index])
        elif opid == ListInsert:
            assert 0 <= index <= len(before), repr((name, index, len(before)))
            opvalue = op[2]
            after = before[:index] + (opvalue,) + before[index:]
            invop = _make_list_delete(index)
        elif opid == ListDelete:
            assert 0 <= index < len(before), repr((name, index, len(before)))
            after = before[:index] + before[index+1:]
            invop = _make_list_insert(index, before[index])
        elif opid == ListMove:
            assert 0 <= index < len(before), repr((name, index, len(before)))
            newindex = op[2]
            assert 0 <= newindex < len(before), repr((name, index, len(before)))
            after = _list_move(before, index, newindex)
            invop = _make_list_move(newindex, index)
        else:
            assert False, repr((name, op))  # pragma: no cover
        return invop, after

    @classmethod
    def from_json(cls, val):
        assert isinstance(val, list) and len(val) >= 3, repr(val)
        op, tid, recordid = val[:3]
        if op == INSERT:
            assert len(val) == 4, repr(val)
            data = dict((field, _value_from_json(v)) for field, v in val[3].items())
        elif op == UPDATE:
            assert len(val) == 4, repr(val)
            data = dict((field, _op_from_json(v)) for field, v in val[3].items())
        elif op == DELETE:
            assert len(val) == 3, repr(val)
            data = None
        else:
            assert False, repr(val)  # pragma: no cover
        return cls(op, tid, recordid, data)

    def to_json(self):
        # We never serialize the undo info.
        if self.op == INSERT:
            data = dict(self.data)
            for k, v in data.items():
                data[k] = _value_to_json(v)
            return [self.op, self.tid, self.recordid, data]
        if self.op == UPDATE:
            data = {}
            for k, v in self.data.items():
                assert _is_op(v), repr(v)
                data[k] = _op_to_json(v)
            return [self.op, self.tid, self.recordid, data]
        if self.op == DELETE:
            return [DELETE, self.tid, self.recordid]
        assert False, repr(self)  # pragma: no cover


# Field ops.
ValuePut, ValueDelete = VALUE_OPS = 'P', 'D'
ListCreate, ListPut, ListInsert, ListDelete, ListMove = LIST_OPS = 'LC', 'LP', 'LI', 'LD', 'LM'

# Sets of field ops.
VALUE_OPS = frozenset(VALUE_OPS)
LIST_OPS = frozenset(LIST_OPS)
ALL_OPS = VALUE_OPS | LIST_OPS

# Codes for encoding special values.
INTEGER = 'I'
NUMBER = 'N'
TIMESTAMP = 'T'
BLOB = 'B'

# Special floating point representations.
PLUS_INFINITY = {NUMBER: '+inf'}
MINUS_INFINITY = {NUMBER: '-inf'}
NOT_A_NUMBER = {NUMBER: 'nan'}

# Special floating point values.
INF_VALUE = 1e1000
NINF_VALUE = -INF_VALUE
NAN_VALUE = INF_VALUE / INF_VALUE


def _new_uuid():
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode('ascii').rstrip('=')


def _value_from_json(v):
    if isinstance(v, (int, long)) and not isinstance(v, bool):
        return float(v)  # Plain JSON "numbers" are only used to encode floats.
    if isinstance(v, dict):
        assert len(v) == 1, repr(v)
        # This slightly awkward spelling is needed to support Python 2 and 3.
        key = next(iter(v))
        val = v[key]
        if key == INTEGER:
            return int(val)
        if key == NUMBER:
            if v == NOT_A_NUMBER:
                return NAN_VALUE
            if v == PLUS_INFINITY:
                return INF_VALUE
            if v == MINUS_INFINITY:
                return NINF_VALUE
            assert False, repr(v)  # pragma: no cover
        if key == TIMESTAMP:
            return Date.from_json(v)
        if key == BLOB:
            return Bytes.from_json(v)
        assert False, repr(v)  # pragma: no cover
    return v


def _value_to_json(v):
    if isinstance(v, (int, long)) and not isinstance(v, bool):
        return {INTEGER: str(v)}
    if isinstance(v, float):
        if math.isinf(v):
            if v > 0:
                return PLUS_INFINITY
            else:
                return MINUS_INFINITY
        if math.isnan(v):
            return NOT_A_NUMBER
    if isinstance(v, (Bytes, Date)):
        return v.to_json()
    return v


def _op_from_json(val):
    assert _is_op(val), repr(val)
    opid = val[0]
    if opid == ValuePut:
        return [opid, _value_from_json(val[1])]
    if opid in (ListPut, ListInsert):
        return [opid, val[1], _value_from_json(val[2])]
    return list(val)


def _op_to_json(val):
    assert _is_op(val), repr(val)
    opid = val[0]
    if opid == ValuePut:
        return [opid, _value_to_json(val[1])]
    if opid in (ListPut, ListInsert):
        return [opid, val[1], _value_to_json(val[2])]
    return list(val)


def _get_op_value(op):
    assert _is_op(op), repr(op)
    opid = op[0]
    if opid == ValuePut:
        return op[1]
    if opid in (ListPut, ListInsert):
        return op[2]
    return None


def _is_op(val):
    return isinstance(val, list) and val and val[0] in ALL_OPS


def _is_listop(val):
    return isinstance(val, list) and val and val[0] in LIST_OPS


def _list_move(old, index, newindex):
    if index <= newindex:
        return (old[:index] + old[index+1:newindex+1] +
                old[index:index+1] + old[newindex+1:])
    else:
        return(old[:newindex] + old[index:index+1] +
               old[newindex:index] + old[index+1:])


def _make_list_create():
    return [ListCreate]


def _make_list_put(index, value):
    return [ListPut, index, value]


def _make_list_insert(index, value):
    return [ListInsert, index, value]


def _make_list_delete(index):
    return [ListDelete, index]


def _make_list_move(index, newindex):
    return [ListMove, index, newindex]
