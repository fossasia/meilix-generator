"""Tests for datastore.py.

Run by 'python setup.py test' in the parent directory.

Or, if you have the right 'mock' module installed or in your
$PYTHONPATH, you can run just this file using
'python -m tests.test_datastore'
(again in the parent directory).
"""

import array
import datetime
import json
import math
import re
import sys
import time
import unittest

PY3 = sys.version_info[0] == 3

if PY3:
    from unittest import mock
    unicode = str
else:
    import mock  # Third-party backport.

from dropbox import rest, datastore
Datastore = datastore.Datastore

# Polyfill a few things for Bytes().
if PY3:
    buffer = memoryview
    basestring = str
    long = int


class ChangesBuilder(object):
    """Helper class to build a list of changes with minimal fuss."""

    def __init__(self, tid='t1'):
        self.tid = tid
        self.changes = []

    def insert(self, rowid, **data):
        assert isinstance(rowid, basestring)
        self.changes.append(datastore._Change(datastore.INSERT, self.tid, rowid, data))

    def update(self, rowid, **data):
        assert isinstance(rowid, basestring)
        # Use _foo=1 to place foo=1 in the undo dict.
        undo = {}
        for k, v in data.items():
            if k.startswith('_'):
                undo[k[1:]] = v
                del data[k]
        for k in data:
            if k not in undo:
                undo[k] = None
        for k in undo:
            if k not in data:
                data[k] = None
        for k, v in data.items():
            if v is None:
                data[k] = [datastore.ValueDelete]
            else:
                data[k] = [datastore.ValuePut, v]
        self.changes.append(datastore._Change(datastore.UPDATE, self.tid, rowid, data, undo))

    def delete(self, rowid, **undo):
        assert isinstance(rowid, basestring)
        self.changes.append(datastore._Change(datastore.DELETE, self.tid, rowid, None, undo))

    def list_op(self, opid, rowid, field, index=None, value=None, newindex=None, old=None):
        if opid == 'Create':
            op = datastore._make_list_create()
        elif opid == 'Put':
            op = datastore._make_list_put(index, value)
        elif opid == 'Insert':
            op = datastore._make_list_insert(index, value)
        elif opid == 'Delete':
            op = datastore._make_list_delete(index)
        elif opid == 'Move':
            op = datastore._make_list_move(index, newindex)
        else:
            assert False, opid

        undo = {field: old} if opid == 'Create' or old is not None else None
        change = datastore._Change(datastore.UPDATE, self.tid, rowid,
                             data={field: op}, undo=undo)
        self.changes.append(change)


def assertRegexpMatches(string, pattern):
    if not re.match(pattern, string):
        raise AssertionError('string %r does not match pattern %r' % (string, pattern))


class TestDatastoreManager(unittest.TestCase):
    """Tests for DatastoreMananger."""

    def setUp(self):
        self.client = mock.Mock()
        self.client.request.return_value = ('', {}, [])  # Dummy url, params, headers.
        self.manager = datastore.DatastoreManager(self.client)

    def test_close(self):
        self.manager.close()
        self.manager.close()

    def test_repr(self):
        self.assertEqual(repr(self.manager), 'DatastoreManager(%r)' % self.client)
        self.manager.close()
        self.assertEqual(repr(self.manager), 'DatastoreManager(None)')

    def test_get_client(self):
        self.assertTrue(self.manager.get_client() is self.client)

    def test_open_default_datastore(self):
        # setup mocks
        self.client.rest_client.POST.return_value = {'rev': 1, 'handle': 'deadbeef'}
        self.client.rest_client.GET.return_value = {'rev': 1, 'rows': []}

        # invoke code
        ds = self.manager.open_default_datastore()

        # check code
        self.assertTrue(isinstance(ds, datastore.Datastore))
        self.assertEqual(ds._rev, 1)
        self.assertEqual(ds.get_id(), datastore.DatastoreManager.DEFAULT_DATASTORE_ID)

    def test_open_datastore(self):
        # setup mocks
        self.client.rest_client.GET.return_value = {'rev': 0, 'handle': 'deadbeef'}

        # invoke code
        ds = self.manager.open_datastore('xyzzy')

        # check code
        self.assertTrue(isinstance(ds, datastore.Datastore))
        self.assertEqual(ds.get_id(), 'xyzzy')

    def test_open_or_create_datastore(self):
        # setup mocks
        self.client.rest_client.POST.return_value = {'rev': 1, 'handle': 'deadbeef'}
        self.client.rest_client.GET.return_value = {'rev': 1, 'rows': []}

        # invoke code
        ds = self.manager.open_or_create_datastore('xyzzy')

        # check code
        self.assertTrue(isinstance(ds, datastore.Datastore))
        self.assertEqual(ds._rev, 1)
        self.assertEqual(ds.get_id(), 'xyzzy')

    def test_bad_datastore_id(self):
        self.assertRaises(ValueError, self.manager.open_datastore, '@')
        self.assertRaises(ValueError, self.manager.open_or_create_datastore, '@')
        self.assertRaises(ValueError, self.manager.open_or_create_datastore, '.foo')

    def test_open_raw_datastore(self):
        ds = self.manager.open_raw_datastore('xyzzy', 'deadbeef')
        self.assertTrue(isinstance(ds, datastore.Datastore))
        self.assertEqual(ds.get_id(), 'xyzzy')
        self.assertEqual(ds.get_handle(), 'deadbeef')
        self.assertEqual(ds.get_rev(), 0)
        self.assertFalse(self.client.rest_client.GET.called)

    def test_create_datastore(self):
        # setup mocks
        self.client.rest_client.POST.return_value = {'rev': 0, 'handle': 'deadbeef'}

        # invoke code
        ds = self.manager.create_datastore()

        # check code
        self.assertTrue(isinstance(ds, datastore.Datastore))
        self.assertTrue(isinstance(ds.get_id(), str))
        assertRegexpMatches(ds.get_id(), r'^\.?[-_0-9a-zA-Z]{1,100}$')  # Too relaxed.

    def test_delete_datastore(self):
        # setup mocks
        self.client.rest_client.GET.return_value = {'rev': 0, 'handle': 'deadbeef'}
        self.client.rest_client.POST.return_value = {
            'ok': "Deleted datastore with handle: 'deadbeef'."}

        # invoke code
        self.manager.delete_datastore('xyzzy')

        # check code
        self.client.rest_client.GET.assert_called_with('', [])
        self.client.rest_client.POST.assert_called_with('', {}, [])

    def make_some_dsinfos(self):
        return [{'dsid': 'default', 'handle': 'deadbeef', 'rev': 42,
                 'info': {'title': 'Esq.', 'mtime': {'T': '1000000000000'}}},
                {'dsid': 'xyzzy', 'handle': '12345678', 'rev': 0},
                ]

    def test_list_datastore(self):
        # setup mocks
        self.client.rest_client.GET.return_value = {'datastores': self.make_some_dsinfos(),
                                                    'token': 'notch'}

        # invoke code
        infos = self.manager.list_datastores()

        # check code
        info0 = infos[0]
        self.assertEqual(info0.id, 'default')
        self.assertEqual(info0.rev, 42)
        self.assertEqual(info0.handle, 'deadbeef')
        self.assertEqual(info0.title, 'Esq.')
        self.assertEqual(info0.mtime, datastore.Date(1000000000))
        info1 = infos[1]
        self.assertEqual(info1.id, 'xyzzy')
        self.assertEqual(info1.rev, 0)
        self.assertEqual(info1.handle, '12345678')
        self.assertEqual(info1.title, None)
        self.assertEqual(info1.mtime, None)

    def test_await_default(self):
        # setup mocks
        self.client.rest_client.POST.return_value = {
            'list_datastores': {'token': 'notch', 'datastores': self.make_some_dsinfos()},
            }

        # invoke code
        token, dsinfos, deltamap = self.manager.await()

        # check code
        self.assertEqual(token, 'notch')
        self.assertEqual(len(dsinfos), 2)
        self.assertTrue(all(isinstance(i, datastore.DatastoreInfo) for i in dsinfos))
        self.client.request.assert_called_with('/datastores/await', {}, method='POST')

    def test_await_token(self):
        # setup mocks
        self.client.rest_client.POST.return_value = {
            'list_datastores': {'token': 'notch', 'datastores': []},
            }

        # invoke code
        token, dsinfos, deltamap = self.manager.await('notch')

        # check code
        self.assertEqual(token, 'notch')
        self.assertEqual(dsinfos, [])
        self.client.request.assert_called_with('/datastores/await',
                                               {'list_datastores': '{"token": "notch"}'},
                                               method='POST')

    def test_await_datastores(self):
        ds = datastore.Datastore(self.manager, id='default', handle='deadbeef')
        rawinfo = self.make_some_dsinfos()[0]
        dsinfo = datastore._make_dsinfo(rawinfo)

        # setup mocks
        self.client.rest_client.POST.return_value = {
            'list_datastores': {'token': 'notch', 'datastores': [rawinfo]},
            'get_deltas': {'deltas': {'deadbeef': {'deltas': []}}},
            }

        # invoke code
        token, dsinfos, deltamap = self.manager.await('notch', [ds])

        # check code
        self.assertEqual(token, 'notch')
        self.assertEqual(dsinfos, [dsinfo])
        self.client.request.assert_called_with('/datastores/await',
                                               {'list_datastores': '{"token": "notch"}',
                                                'get_deltas': '{"cursors": {"deadbeef": 0}}',
                                                },
                                               method='POST')
        self.assertEqual(deltamap, {ds: []})

    def test_await_datastores_mapping(self):
        ds = datastore.Datastore(self.manager, id='default', handle='deadbeef')
        rawinfo = self.make_some_dsinfos()[0]
        dsinfo = datastore._make_dsinfo(rawinfo)

        # setup mocks
        self.client.rest_client.POST.return_value = {
            'list_datastores': {'token': 'notch', 'datastores': [rawinfo]},
            'get_deltas': {'deltas': {'deadbeef': {'deltas': []}}},
            }

        # invoke code
        token, dsinfos, deltamap = self.manager.await('notch', {ds: 42})

        # check code
        self.assertEqual(token, 'notch')
        self.assertEqual(dsinfos, [dsinfo])
        self.client.request.assert_called_with('/datastores/await',
                                               {'list_datastores': '{"token": "notch"}',
                                                'get_deltas': '{"cursors": {"deadbeef": 42}}',
                                                },
                                               method='POST')
        self.assertEqual(deltamap, {ds: []})

    def test_await_datastores_notfound(self):
        ds = datastore.Datastore(self.manager, id='default', handle='deadbeef')
        rawinfo = self.make_some_dsinfos()[0]
        dsinfo = datastore._make_dsinfo(rawinfo)

        # setup mocks
        self.client.rest_client.POST.return_value = {
            'list_datastores': {'token': 'notch', 'datastores': [rawinfo]},
            'get_deltas': {'deltas': {'deadbeef': {'notfound': 'error message'}}},
            }

        # invoke code
        token, dsinfos, deltamap = self.manager.await('notch', [ds])

        # check code
        self.assertEqual(token, 'notch')
        self.assertEqual(dsinfos, [dsinfo])
        self.client.request.assert_called_with('/datastores/await',
                                               {'list_datastores': '{"token": "notch"}',
                                                'get_deltas': '{"cursors": {"deadbeef": 0}}',
                                                },
                                               method='POST')
        self.assertEqual(deltamap, {ds: None})

    def test_make_cursor_map(self):
        make_cursor_map = datastore.DatastoreManager.make_cursor_map
        ds1 = datastore.Datastore(self.manager, id='default', handle='deadbeef')
        ds1._rev = 1
        ds2 = datastore.Datastore(self.manager, id='default', handle='deadbaad')
        ds2._rev = 2

        self.assertEqual(make_cursor_map([ds1, ds2], None),
                         {ds1: 1, ds2: 2})
        self.assertEqual(make_cursor_map([ds1, ds2], {}),
                         {ds1: 1, ds2: 2})
        self.assertEqual(make_cursor_map([ds1, ds2], {ds1: None}),
                         {ds2: 2})
        self.assertEqual(make_cursor_map([ds1, ds2], {ds2: [{'rev': 2, 'changes': []}]}),
                         {ds1: 1, ds2: 3})

    def test_dsops_errors(self):
        # White-box test for obscure error checks.
        dsops = self.manager._dsops
        self.assertRaises(datastore.DatastoreError, dsops._check_access_errors, {'notfound': 'x'})
        self.assertRaises(datastore.DatastoreError, dsops._check_access_errors, {'access_denied': 'x'})
        self.assertRaises(datastore.DatastoreError, dsops._check_rev, {})
        self.assertRaises(datastore.DatastoreError, dsops._check_handle, {'rev': 0})
        self.assertRaises(datastore.DatastoreError, dsops._check_ok, {})
        self.assertRaises(datastore.DatastoreError, dsops._check_conflict, {'conflict': 'x'})
        self.assertRaises(datastore.DatastoreError, dsops._check_list_datastores, {})
        self.assertRaises(datastore.DatastoreError, dsops._check_get_snapshot, {'rev': 0})
        self.assertRaises(datastore.DatastoreError, dsops._check_get_deltas, {'rev': 0})


class TestDatastoreInfo(unittest.TestCase):
    """Tests for DatastoreInfo."""

    def test_init_minimal(self):
        item = {'dsid': 'default', 'handle': 'deadbeef', 'rev': 0}
        dsinfo = datastore._make_dsinfo(item)
        self.assertEqual(dsinfo.id, 'default')
        self.assertEqual(dsinfo.handle, 'deadbeef')
        self.assertEqual(dsinfo.rev, 0)
        self.assertEqual(dsinfo.title, None)
        self.assertEqual(dsinfo.mtime, None)
        self.assertEqual(dsinfo.effective_role, Datastore.OWNER)

    def test_init_with_empty_info(self):
        item = {'dsid': 'default', 'handle': 'deadbeef', 'rev': 42, 'info': {}}
        dsinfo = datastore._make_dsinfo(item)
        self.assertEqual(dsinfo.id, 'default')
        self.assertEqual(dsinfo.handle, 'deadbeef')
        self.assertEqual(dsinfo.rev, 42)
        self.assertEqual(dsinfo.title, None)
        self.assertEqual(dsinfo.mtime, None)
        self.assertEqual(dsinfo.effective_role, Datastore.OWNER)

    def test_init_with_title_only(self):
        item = {'dsid': 'default', 'handle': 'deadbeef', 'rev': 42, 'info': {'title': 'foo'}}
        dsinfo = datastore._make_dsinfo(item)
        self.assertEqual(dsinfo.id, 'default')
        self.assertEqual(dsinfo.handle, 'deadbeef')
        self.assertEqual(dsinfo.rev, 42)
        self.assertEqual(dsinfo.title, 'foo')
        self.assertEqual(dsinfo.mtime, None)
        self.assertEqual(dsinfo.effective_role, Datastore.OWNER)

    def test_init_with_mtime_only(self):
        item = {'dsid': 'default', 'handle': 'deadbeef', 'rev': 42,
                'info': {'mtime': {'T': '123456789012'}}}
        dsinfo = datastore._make_dsinfo(item)
        self.assertEqual(dsinfo.id, 'default')
        self.assertEqual(dsinfo.handle, 'deadbeef')
        self.assertEqual(dsinfo.rev, 42)
        self.assertEqual(dsinfo.title, None)
        self.assertEqual(dsinfo.mtime, datastore.Date(123456789.0123), dsinfo.mtime)
        self.assertEqual(dsinfo.effective_role, Datastore.OWNER)

    def test_init_with_full_info(self):
        item = {'dsid': 'default', 'handle': 'deadbeef', 'rev': 42,
                'info': {'mtime': {'T': '123456789012'}, 'title': 'foo'}}
        dsinfo = datastore._make_dsinfo(item)
        self.assertEqual(dsinfo.id, 'default')
        self.assertEqual(dsinfo.handle, 'deadbeef')
        self.assertEqual(dsinfo.rev, 42)
        self.assertEqual(dsinfo.title, 'foo')
        self.assertEqual(dsinfo.mtime, datastore.Date(123456789.0123), dsinfo.mtime)
        self.assertEqual(dsinfo.effective_role, Datastore.OWNER)

    def test_init_with_owner_role(self):
        item = {'dsid': '.shared', 'handle': 'deadbeef', 'rev': 42, 'role': datastore.ROLE_OWNER}
        dsinfo = datastore._make_dsinfo(item)
        self.assertEqual(dsinfo.effective_role, Datastore.OWNER)

    def test_init_with_editor_role(self):
        item = {'dsid': '.shared', 'handle': 'deadbeef', 'rev': 42, 'role': datastore.ROLE_EDITOR}
        dsinfo = datastore._make_dsinfo(item)
        self.assertEqual(dsinfo.effective_role, Datastore.EDITOR)

    def test_init_with_viewer_role(self):
        item = {'dsid': '.shared', 'handle': 'deadbeef', 'rev': 42, 'role': datastore.ROLE_VIEWER}
        dsinfo = datastore._make_dsinfo(item)
        self.assertEqual(dsinfo.effective_role, Datastore.VIEWER)

    def test_repr(self):
        item = {'dsid': 'default', 'handle': 'deadbeef', 'rev': 42,
                'info': {'mtime': {'T': '123456789012'}, 'title': 'foo'}}
        dsinfo = datastore._make_dsinfo(item)
        self.assertEqual(repr(dsinfo),
                         "DatastoreInfo(id='default', handle='deadbeef', rev=42, "
                         "title='foo', mtime=Date<1973-11-29 21:33:09.012 UTC>, effective_role='owner')")

    def test_eq_ne(self):
        ds1 = datastore._make_dsinfo({'dsid': 'default', 'handle': 'deadbeef', 'rev': 0})
        ds2 = datastore._make_dsinfo({'dsid': 'default', 'handle': 'deadbeef', 'rev': 0})
        ds3 = datastore._make_dsinfo({'dsid': 'default', 'handle': 'deadbeef', 'rev': 0,
                                      'info': {'mtime': {'T': '123456789012'}}})
        self.assertEqual(ds1, ds2)
        self.assertFalse(ds1 == 42)
        self.assertNotEqual(ds1, ds3)
        self.assertTrue(ds1 != 42)

    def test_eq_shareable(self):
        ds1 = datastore._make_dsinfo({'dsid': '.foo', 'handle': 'deadbeef', 'rev': 0})
        ds2 = datastore._make_dsinfo({'dsid': '.foo', 'handle': 'deadbeef', 'rev': 0, 'role': datastore.ROLE_OWNER})
        self.assertEqual(ds1, ds2)


GOOD_DSIDS = ['1', 'foo', 'x'*64, 'foo.bar', 'foo...bar', '-foo-bar-', '_foo_bar_', '.Foo09-_bar']
BAD_DSIDS = ['', 'A', 'foo@bar.com', 'x'*65, '.', 'foo.', '.foo.bar']


class TestDatastore(unittest.TestCase):
    """Tests for Datastore."""

    def setUp(self):
        self.client = mock.Mock()
        self.client.request.return_value = ('', {}, [])  # Dummy url, params, headers.
        self.manager = datastore.DatastoreManager(self.client)
        self.datastore = datastore.Datastore(self.manager, id='xyzzy', handle='deadbeef')

    def test_repr(self):
        self.assertEqual(repr(self.datastore),
                         "Datastore(<rev=0>, id='xyzzy', handle='deadbeef', role=None)")

    def test_is_valid_id(self):
        for id in GOOD_DSIDS:
            self.assertTrue(datastore.Datastore.is_valid_id(id), id)
        for id in BAD_DSIDS:
            self.assertFalse(datastore.Datastore.is_valid_id(id), id)

    def test_is_valid_shareable_id(self):
        for id in GOOD_DSIDS:
            if id.startswith('.'):
                self.assertTrue(datastore.Datastore.is_valid_shareable_id(id), id)
            else:
                self.assertFalse(datastore.Datastore.is_valid_shareable_id(id), id)
        for id in BAD_DSIDS:
            self.assertFalse(datastore.Datastore.is_valid_shareable_id(id), id)

    def test_get_id(self):
        self.assertEqual(self.datastore.get_id(), 'xyzzy')

    def test_get_handle(self):
        self.assertEqual(self.datastore.get_handle(), 'deadbeef')

    def test_get_rev(self):
        self.assertEqual(self.datastore.get_rev(), 0)

    def test_get_manager(self):
        self.assertTrue(self.datastore.get_manager() is self.manager)

    def test_title(self):
        self.assertEqual(self.datastore.get_title(), None)
        self.datastore.set_title('Foo Bar')
        self.assertEqual(self.datastore.get_title(), 'Foo Bar')
        self.datastore.set_title('Bar Foo')
        self.assertEqual(self.datastore.get_title(), 'Bar Foo')
        self.assertRaises(TypeError, self.datastore.set_title, 42)

    def test_mtime(self):
        self.assertEqual(self.datastore.get_mtime(), None)
        # See test_commit() for checks of mtime.

    def test_load_snapshot(self):
        # setup mocks
        rows = [{'tid': 't1', 'rowid': 'r1', 'data': {'foo': 42}}]
        self.client.rest_client.GET.return_value = {'rev': 2, 'rows': rows}

        # invoke code
        self.datastore.load_snapshot()

        # check code
        self.assertEqual(self.datastore._rev, 2)
        self.assertEqual(self.datastore.list_table_ids(), set(['t1']))
        t = self.datastore.get_table('t1')
        self.assertEqual(t.get('r1').get_fields(), {'foo': 42})

        # check we can apply updates after load
        t.get('r1').update(foo=43)
        self.assertEqual(t.get('r1').get_fields(), {'foo': 43})

    def test_apply_snapshot(self):
        rev = 3
        snapshot = [{'tid': 't1', 'rowid': 'r1', 'data': {'foo': {'I': '0'}}}]
        self.datastore.apply_snapshot(rev, snapshot)
        self.assertEqual(self.datastore.get_rev(), 3)
        self.assertEqual(self.datastore.list_table_ids(), set(['t1']))
        t1 = self.datastore.get_table('t1')
        self.assertEqual(t1.query(), {t1.get('r1')})
        self.assertEqual(t1.get('r1').get_fields(), {'foo': 0})

    def make_some_deltas(self):
        c1 = ChangesBuilder()
        c1.insert('r1', foo=42, baz='abc')
        c1.insert('r2', bar=42)
        c2 = ChangesBuilder()
        c2.delete('r2')
        c3 = ChangesBuilder()
        c3.update('r1', foo=0, baz=None)
        deltas = [{'rev': 0, 'changes': [ch.to_json() for ch in c1.changes]},
                  {'rev': 1, 'changes': [ch.to_json() for ch in c2.changes]},
                  {'rev': 2, 'changes': [ch.to_json() for ch in c3.changes]},
                  ]
        return deltas

    def test_get_snapshot(self):
        deltas = self.make_some_deltas()
        self.datastore.apply_deltas(deltas)
        self.assertEqual(self.datastore.get_rev(), 3)
        self.assertEqual(self.datastore.get_snapshot(),
                         [{'tid': 't1', 'rowid': 'r1', 'data': {'foo': {'I': '0'}}}])

    def test_await_deltas(self):
        # setup mocks
        deltas = self.make_some_deltas()
        self.client.rest_client.POST.return_value = {
            'get_deltas': {'deltas': {self.datastore._handle: {'deltas': deltas}}},
            }

        # invoke code
        out = self.datastore.await_deltas()

        # check code
        t1 = self.datastore.get_table('t1')
        self.assertEqual(out,
                         {'t1': set([datastore.Record(t1, 'r1'),
                                     datastore.Record(t1, 'r2'),
                                     ]),
                          })
        self.assertEqual(self.datastore.list_table_ids(), set(['t1']))
        self.assertEqual(t1.get('r1'), datastore.Record(t1, 'r1'))
        self.assertEqual(t1.get('r2'), None)

    def test_await_deltas_pending_changes(self):
        self.datastore.get_table('t1').get_or_insert('r1')
        self.assertRaises(datastore.DatastoreError, self.datastore.await_deltas)

    def test_await_deltas_no_get_deltas(self):
        # setup mocks
        self.client.rest_client.POST.return_value = {}

        # invoke code
        out = self.datastore.await_deltas()

        # check code
        self.assertEqual(out, {})

    def test_await_deltas_no_handle_key(self):
        # setup mocks
        self.client.rest_client.POST.return_value = {'get_deltas': {'deltas': {}}}

        # invoke code
        out = self.datastore.await_deltas()

        # check code
        self.assertEqual(out, {})

    def test_await_deltas_deleted(self):
        # setup mocks
        self.client.rest_client.POST.return_value = {
            'get_deltas': {'deltas': {self.datastore._handle: {'notfound': 'error message'}}},
            }

        # invoke code
        self.assertRaises(datastore.DatastoreNotFoundError, self.datastore.await_deltas)

    def test_load_deltas(self):
        # setup mocks
        deltas = self.make_some_deltas()
        self.client.rest_client.GET.return_value = {'deltas': deltas}

        # invoke code
        out = self.datastore.load_deltas()

        # check code
        self.assertEqual(self.datastore._rev, 3)
        t1 = self.datastore.get_table('t1')
        self.assertEqual(out,
                         {'t1': set([datastore.Record(t1, 'r1'),
                                     datastore.Record(t1, 'r2'),
                                     ]),
                          })
        self.assertEqual(self.datastore.list_table_ids(), set(['t1']))
        self.assertEqual(t1.get('r1'), datastore.Record(t1, 'r1'))
        self.assertEqual(t1.get('r2'), None)

    def test_load_deltas_pending_changes(self):
        self.datastore.get_table('t1').get_or_insert('r1')
        self.assertRaises(datastore.DatastoreError, self.datastore.load_deltas)

    def test_load_deltas_no_changes(self):
        # setup mocks
        self.client.rest_client.GET.return_value = {}

        # invoke code
        out = self.datastore.load_deltas()

        # check code
        self.assertEqual(out, {})
        self.assertEqual(self.datastore._rev, 0)  # I.e., unchanged.

    def test_apply_deltas(self):
        deltas = self.make_some_deltas()
        out = self.datastore.apply_deltas(deltas)
        self.assertEqual(self.datastore._rev, 3)
        t1 = self.datastore.get_table('t1')
        self.assertEqual(out,
                         {'t1': set([datastore.Record(t1, 'r1'),
                                     datastore.Record(t1, 'r2'),
                                     ]),
                          })
        self.assertEqual(self.datastore.list_table_ids(), set(['t1']))
        self.assertEqual(t1.get('r1'), datastore.Record(t1, 'r1'))
        self.assertEqual(t1.get('r2'), None)

    def test_apply_deltas_no_changes(self):
        out = self.datastore.apply_deltas(None)
        self.assertEqual(out, {})
        self.assertEqual(self.datastore._rev, 0)  # I.e., unchanged.

    def test_apply_deltas_pending_changes(self):
        self.datastore.get_table('t1').get_or_insert('r1')
        deltas = []
        self.assertRaises(datastore.DatastoreError, self.datastore.apply_deltas, deltas)

    def test_apply_deltas_old_rev(self):
        deltas = self.make_some_deltas()
        # Apply the first two of three deltas.
        out = self.datastore.apply_deltas(deltas[:2])
        self.assertEqual(self.datastore._rev, 2)
        t1 = self.datastore.get_table('t1')
        self.assertEqual(out,
                         {'t1': set([datastore.Record(t1, 'r1'),
                                     datastore.Record(t1, 'r2'),
                                     ]),
                          })
        self.assertEqual(t1.get('r1').get_fields(), {'foo': 42, 'baz': 'abc'})
        self.assertEqual(t1.get('r2'), None)
        # Re-apply all three deltas.  Only the last should have an effect.
        out = self.datastore.apply_deltas(deltas)
        self.assertEqual(out, {'t1': set([datastore.Record(t1, 'r1')])})
        self.assertEqual(t1.get('r1').get_fields(), {'foo': 0})

    def test_apply_deltas_out_of_order_rev(self):
        deltas = [{'rev': 42, 'changes': []}]
        self.assertRaises(datastore.DatastoreError, self.datastore.apply_deltas, deltas)

    def test_get_table(self):
        t1 = self.datastore.get_table('t1')
        self.assertTrue(isinstance(t1, datastore.Table))
        self.assertEqual(t1.get_id(), 't1')

        # Getting it again should return the same object.
        t2 = self.datastore.get_table('t1')
        self.assertTrue(t1 is t2)

        # Getting another should of course return a different object.
        t3 = self.datastore.get_table('t3')
        self.assertTrue(t2 is not t3)

    def test_bad_table_id(self):
        self.assertRaises(ValueError, self.datastore.get_table, '@')

    def test_list_table_ids(self):
        ids = self.datastore.list_table_ids()
        self.assertEqual(ids, set())

        # Creating empty table objects doesn't affect list_table_ids().
        t1 = self.datastore.get_table('t1')
        t2 = self.datastore.get_table('t2')
        ids = self.datastore.list_table_ids()
        self.assertEqual(ids, set())

        # But inserting records does.
        t1.insert(foo=42)
        t2.insert(bar='abc')
        ids = self.datastore.list_table_ids()
        self.assertEqual(ids, set(['t1', 't2']))

    def test_rollback(self):
        t1 = self.datastore.get_table('t1')
        t2 = self.datastore.get_table('t2')
        r1 = t1.insert(foo=42)
        r2 = t2.insert(bar='abc')
        self.assertEqual(len(self.datastore._changes), 2)  # Just checkin'.
        self.assertEqual(t1.query(), set([r1]))
        self.assertEqual(t2.query(), set([r2]))
        self.datastore.rollback()
        self.assertEqual(len(self.datastore._changes), 0)
        self.assertEqual(self.datastore.list_table_ids(), set())
        self.assertEqual(t1.query(), set())
        self.assertEqual(t2.query(), set())

    def test_commit(self):
        t1 = self.datastore.get_table('t1')
        t2 = self.datastore.get_table('t2')
        r1 = t1.insert(foo=42)
        r2 = t2.insert(bar='abc')
        self.assertEqual(len(self.datastore._changes), 2)  # Just checkin'.

        # setup mocks
        self.client.rest_client.POST.return_value = {'rev': 1}

        # invoke code
        self.datastore.commit()

        # check code
        self.assertEqual(self.datastore._rev, 1)
        self.assertEqual(self.datastore._changes, [])

        # Check that mtime was set.
        self.assertTrue(isinstance(self.datastore.get_mtime(), datastore.Date))

        # Pick apart request call args.  This is a bit overspecified
        # but not too much, and we really do want to make reasonably
        # sure that we sent the right values to put_delta.
        args, kwargs = self.client.request.call_args
        path, params = args
        assertRegexpMatches(path, '^/.*/put_delta$')
        self.assertEqual(params['handle'], 'deadbeef')
        self.assertEqual(params['rev'], '0')
        changes = json.loads(params['changes'])
        self.assertEqual(len(changes), 4)
        ins1 = changes[0]
        self.assertEqual(ins1[:2], [datastore.INSERT, 't1'])
        self.assertEqual(ins1[3], {'foo': datastore._value_to_json(42)})
        ins2 = changes[1]
        self.assertEqual(ins2[:2], [datastore.INSERT, 't2'])
        self.assertEqual(ins2[3], {'bar': 'abc'})
        # The final two changes update the metadata in the :info table.
        # Don't check these.

    def test_commit_conflict(self):
        r1 = self.datastore.get_table('t1').insert(foo=42)

        # setup mocks
        self.client.rest_client.POST.return_value = {'conflict': 'a conflict error'}

        # invoke code
        self.assertRaises(datastore.DatastoreConflictError, self.datastore.commit)

        # check code
        self.assertEqual(self.datastore._rev, 0)  # I.e., unchanged.

    def test_commit_no_changes(self):
        self.datastore.commit()
        # POST should *not* be called.
        self.assertFalse(self.client.rest_client.POST.called)

    def test_transaction(self):
        attempts = []
        def callback(t1):
            r1 = t1.insert(foo=42)
            attempts.append(r1)
            return r1

        # setup mocks -- first POST is a conflict, second succeeds
        conflict = datastore.DatastoreConflictError('conflict', None)
        self.client.rest_client.POST.side_effect = [conflict, {'rev': 1}]
        self.client.rest_client.GET.return_value = {'deltas': []}

        # invoke code
        t1 = self.datastore.get_table('t1')
        r1 = self.datastore.transaction(callback, t1, max_tries=2)

        # check code
        self.assertEqual(len(attempts), 2)
        self.assertTrue(r1 is attempts[1])
        self.assertEqual(r1.get_fields(), {'foo': 42})
        self.assertTrue(t1.get('r1') is None)  # Since it got deleted.
        self.assertFalse(t1.get('r2') == attempts[1])  # Since it got committed.

        # check that there were two POST calls (i.e. put_deltas) and
        # one GET (i.e. get_deltas).
        self.client.rest_client.POST.assert_has_calls([mock.call('', {}, [])]*2)
        self.client.rest_client.GET.assert_called_once_with('', [])

    def test_transaction__exceeds_tries(self):
        attempts = []
        def callback():
            self.datastore.get_table('t1').get_or_insert('r1')
            attempts.append(len(attempts))

        # setup mocks -- POST fails every time.
        conflict = datastore.DatastoreConflictError('conflict', None)
        self.client.rest_client.POST.side_effect = conflict
        self.datastore.load_deltas = mock.Mock()

        # invoke code
        try:
            self.datastore.transaction(callback)
        except datastore.DatastoreError as raised:
            # check code
            self.assertEqual(attempts, [0])
            self.assertEqual(str(raised),
                             'Failed to commit; set max_tries to a value > 1 to retry')
        else:
            self.fail('Expected datastore.DatastoreError')

    def test_transaction__set_max_tries(self):
        attempts = []
        def callback():
            self.datastore.get_table('t1').get_or_insert('r1')
            attempts.append(len(attempts))

        # setup mocks -- POST fails every time.
        conflict = datastore.DatastoreConflictError('conflict', None)
        self.client.rest_client.POST.side_effect = conflict
        self.datastore.load_deltas = mock.Mock()

        # invoke code
        try:
            self.datastore.transaction(callback, max_tries=2)
        except datastore.DatastoreError as raised:
            # check code
            self.assertEqual(attempts, [0, 1])
            self.assertEqual(str(raised), 'Failed to commit 2 times in a row')
        else:
            self.fail('Expected datastore.DatastoreError')

    def test_transaction__callback_fails(self):
        def callback():
            raise ZeroDivisionError

        # setup mocks -- rollback() must be called
        self.datastore.rollback = mock.Mock()

        # invoke code
        self.assertRaises(ZeroDivisionError, self.datastore.transaction, callback)

        # check code
        self.datastore.rollback.assert_called_once()

    def test_transaction__commit_fails(self):
        attempts = []
        def callback():
            self.datastore.get_table('t1').get_or_insert('r1')
            attempts.append(len(attempts))

        # setup mocks -- POST fails every time.
        self.client.rest_client.POST.side_effect = RuntimeError('fail')
        self.datastore.load_deltas = mock.Mock()

        # invoke code
        try:
            self.datastore.transaction(callback, max_tries=2)
        except RuntimeError as raised:
            # check code
            self.assertEqual(attempts, [0])
            self.assertEqual(str(raised), 'fail')
        else:
            self.fail('Expected RuntimeError')

    def test_transaction__pending_changes(self):
        def callback():
            pass
        self.datastore.get_table('t1').get_or_insert('r1')
        try:
            self.datastore.transaction(callback)
        except datastore.DatastoreError as raised:
            self.assertEqual(str(raised), 'There should be no pending changes')
        else:
            self.fail('Expected datastore.DatastoreError')

    def test_transaction__bad_max_tries(self):
        def callback():
            pass
        self.assertRaises(ValueError, self.datastore.transaction, callback, max_tries=-1)
        self.assertRaises(ValueError, self.datastore.transaction, callback, max_tries=0)

    def test_transaction__bad_kwargs(self):
        try:
            self.datastore.transaction(lambda: None, extra=42, max_tries=1)
        except TypeError as raised:
            self.assertEqual(str(raised), "Unexpected kwargs {'extra': 42}")
        else:
            self.fail('Expected TypeError')

    def test_close(self):
        self.datastore.close()
        self.datastore.close()
        self.assertRaises(Exception, self.datastore.get_table('t1').get_or_insert, 'r1')
        self.assertRaises(Exception, self.datastore.load_deltas)


class TestPrincipal(unittest.TestCase):
    """Tests for Principal."""

    def test_eq_ne(self):
        self.assertEqual(Datastore.TEAM, Datastore.TEAM)
        self.assertEqual(datastore.User(42), datastore.User(42))
        self.assertNotEqual(Datastore.TEAM, Datastore.PUBLIC)
        self.assertNotEqual(datastore.User(1), datastore.User(2))
        self.assertNotEqual(Datastore.TEAM, 'team')
        self.assertNotEqual(datastore.User(42), 42)
        self.assertFalse(Datastore.TEAM == None)  # Test NotImplemented in __eq__.

    def test_user(self):
        with self.assertRaises(ValueError):
            datastore.User('hohoho')
        self.assertEqual(datastore.User('42'), datastore.User(42))
        with self.assertRaises(ValueError):
            datastore.User('042')
        with self.assertRaises(ValueError):
            datastore.User('+42')
        with self.assertRaises(ValueError):
            datastore.User('0')
        with self.assertRaises(ValueError):
            datastore.User(0)
        with self.assertRaises(ValueError):
            datastore.User(-1)
        with self.assertRaises(TypeError):
            datastore.User(42.0)

    def test_repr(self):
        self.assertEqual(repr(Datastore.TEAM), 'TEAM')
        self.assertEqual(repr(Datastore.PUBLIC), 'PUBLIC')
        self.assertEqual(repr(datastore.User(42)), 'User(42)')


class TestSharing(unittest.TestCase):
    """Tests for sharing functionality."""

    def setUp(self):
        self.client = mock.Mock()
        self.client.request.return_value = ('', {}, [])  # Dummy url, params, headers.
        self.manager = datastore.DatastoreManager(self.client)

    def test_make_role(self):
        self.assertEqual(datastore._make_role(None), Datastore.OWNER)
        self.assertEqual(datastore._make_role(datastore.ROLE_OWNER+1), Datastore.OWNER)
        self.assertEqual(datastore._make_role(datastore.ROLE_OWNER), Datastore.OWNER)
        self.assertEqual(datastore._make_role(datastore.ROLE_OWNER-1), Datastore.EDITOR)
        self.assertEqual(datastore._make_role(datastore.ROLE_EDITOR), Datastore.EDITOR)
        self.assertEqual(datastore._make_role(datastore.ROLE_EDITOR-1), Datastore.VIEWER)
        self.assertEqual(datastore._make_role(datastore.ROLE_VIEWER), Datastore.VIEWER)
        self.assertEqual(datastore._make_role(datastore.ROLE_VIEWER-1), Datastore.NONE)
        self.assertEqual(datastore._make_role(0), Datastore.NONE)
        self.assertEqual(datastore._make_role(-1), Datastore.NONE)
        with self.assertRaises(TypeError):
            datastore._make_role(Datastore.OWNER)

    def test_parse_role(self):
        self.assertEqual(datastore._parse_role(Datastore.OWNER, owner_ok=True), datastore.ROLE_OWNER)
        self.assertEqual(datastore._parse_role(Datastore.EDITOR), datastore.ROLE_EDITOR)
        self.assertEqual(datastore._parse_role(Datastore.VIEWER), datastore.ROLE_VIEWER)
        self.assertEqual(datastore._parse_role(Datastore.NONE), datastore.ROLE_NONE)
        with self.assertRaises(ValueError):
            datastore._parse_role(Datastore.OWNER)  # owner_ok=False
        with self.assertRaises(ValueError):
            datastore._parse_role('x')
        with self.assertRaises(TypeError):
            datastore._parse_role(42)
        with self.assertRaises(TypeError):
            datastore._parse_role(None)

    def test_roles_private_datastore(self):
        ds = datastore.Datastore(self.manager, 'foo', 'deadbeef')
        # get_effective_role() always returns OWNER
        self.assertEqual(ds.get_effective_role(), Datastore.OWNER)
        # is_writable() is always True
        self.assertTrue(ds.is_writable())
        # Other role APIs raise
        with self.assertRaises(datastore.DatastoreError):
            ds.get_role(Datastore.PUBLIC)
        with self.assertRaises(datastore.DatastoreError):
            ds.set_role(Datastore.PUBLIC, Datastore.VIEWER)
        with self.assertRaises(datastore.DatastoreError):
            ds.delete_role(Datastore.PUBLIC)
        with self.assertRaises(datastore.DatastoreError):
            ds.list_roles()

    def test_roles_shareable_datastore(self):
        ds = datastore.Datastore(self.manager, '.foo', 'deadbeef', Datastore.OWNER)
        self.assertEqual(ds.get_effective_role(), Datastore.OWNER)
        self.assertTrue(ds.is_writable())
        self.assertEqual(ds.get_role(Datastore.PUBLIC), Datastore.NONE)
        self.assertEqual(ds.list_roles(), {})
        ds.set_role(Datastore.PUBLIC, Datastore.VIEWER)
        ds.set_role(Datastore.TEAM, Datastore.EDITOR)
        ds.set_role(datastore.User(42), Datastore.EDITOR)
        ds.set_role(datastore.User(42), Datastore.VIEWER)  # Override.
        ds.set_role(datastore.User(43), Datastore.VIEWER)
        ds.delete_role(datastore.User(43))
        self.assertEqual(ds.get_role(Datastore.PUBLIC), Datastore.VIEWER)
        self.assertEqual(ds.get_role(Datastore.TEAM), Datastore.EDITOR)
        self.assertEqual(ds.get_role(datastore.User(42)), Datastore.VIEWER)
        self.assertEqual(ds.get_role(datastore.User(43)), Datastore.NONE)
        self.assertEqual(ds.list_roles(), {Datastore.PUBLIC: Datastore.VIEWER,
                                           Datastore.TEAM: Datastore.EDITOR,
                                           datastore.User(42): Datastore.VIEWER})
        ds.set_role(datastore.User(42), Datastore.NONE)
        self.assertEqual(ds.get_role(datastore.User(42)), Datastore.NONE)
        with self.assertRaises(TypeError):
            ds.get_role('TEAM')
        with self.assertRaises(TypeError):
            ds.set_role('TEAM', Datastore.EDITOR)
        with self.assertRaises(TypeError):
            ds.delete_role('TEAM')
        with self.assertRaises(TypeError):
            ds.get_role(2000)
        with self.assertRaises(ValueError):
            ds.set_role(Datastore.TEAM, Datastore.OWNER)
        with self.assertRaises(ValueError):
            ds.set_role(Datastore.TEAM, 'woner')
        with self.assertRaises(TypeError):
            ds.set_role(Datastore.TEAM, 3000)
        with self.assertRaises(TypeError):
            ds.set_role(Datastore.TEAM, None)

    def test_open_raw(self):
        with self.assertRaises(TypeError):
            self.manager.open_raw_datastore('foo', 'deadbeef', 42)
        with self.assertRaises(ValueError):
            self.manager.open_raw_datastore('foo', 'deadbeef', 'x')
        ds = self.manager.open_raw_datastore('foo', 'deadbeef')
        self.assertEqual(ds.get_effective_role(), Datastore.OWNER)
        ds = self.manager.open_raw_datastore('foo', 'deadbeef', Datastore.OWNER)
        self.assertEqual(ds.get_effective_role(), Datastore.OWNER)
        with self.assertRaises(ValueError):
            self.manager.open_raw_datastore('foo', 'deadbeef', Datastore.EDITOR)
        ds = self.manager.open_raw_datastore('.foo', 'deadbeef')
        self.assertEqual(ds.get_effective_role(), Datastore.OWNER)
        ds = self.manager.open_raw_datastore('.foo', 'deadbeef', Datastore.OWNER)
        self.assertEqual(ds.get_effective_role(), Datastore.OWNER)

    def test_access_editor(self):
        ds = datastore.Datastore(self.manager, '.foo', 'deadbeef', Datastore.OWNER)
        self.assertEqual(ds.get_effective_role(), Datastore.OWNER)
        self.assertTrue(ds.is_writable())
        tab = ds.get_table('tab')
        rec = tab.insert()
        rec.update(foo=42)
        rec.delete_record()

    def test_access_viewer(self):
        ds = datastore.Datastore(self.manager, '.foo', 'deadbeef', Datastore.VIEWER)
        self.assertEqual(ds.get_effective_role(), Datastore.VIEWER)
        self.assertFalse(ds.is_writable())
        tab = ds.get_table('tab')
        with self.assertRaises(datastore.DatastorePermissionError):
            tab.insert()
        # White box test inserts a record, then attempts to modify it.
        tab._records['foo'] = datastore.Record(tab, 'foo')
        rec = tab.get('foo')
        with self.assertRaises(datastore.DatastorePermissionError):
            rec.update(foo=42)
        with self.assertRaises(datastore.DatastorePermissionError):
            rec.delete_record()


GOOD_IDS = ['1', 'foo', 'Foo-_+.=Bar', 'x'*64, ':foo', ':' + 'x'*63]
BAD_IDS = ['', 'foo@bar.com', 'x'*65, ':', ':' + 'x'*64]


class TestTable(unittest.TestCase):
    """Tests for Table."""

    def setUp(self):
        self.client = mock.Mock()
        self.client.request.return_value = ('', {}, [])  # Dummy url, params, headers.
        self.manager = datastore.DatastoreManager(self.client)
        self.datastore = datastore.Datastore(self.manager, id='xyzzy', handle='deadbeef')
        self.table = self.datastore.get_table('t1')

    def test_repr(self):
        self.assertEqual(repr(self.table), "Table(<xyzzy>, 't1')")

    def test_is_valid_id(self):
        for id in GOOD_IDS:
            self.assertTrue(datastore.Table.is_valid_id(id), id)
        for id in BAD_IDS:
            self.assertFalse(datastore.Table.is_valid_id(id), id)

    def test_get_id(self):
        self.assertEqual(self.table.get_id(), 't1')

    def test_get_datastore(self):
        self.assertTrue(self.table.get_datastore() is self.datastore)

    def test_get_and_get_or_insert(self):
        self.assertEqual(self.table.get('r1'), None)
        r1 = self.table.get_or_insert('r1', foo=42)
        r2 = self.table.get_or_insert('r1', foo=42)
        r3 = self.table.get('r1')
        self.assertEqual(r1, r2)
        self.assertEqual(r2, r3)
        self.assertEqual(r3, r1)

        # White box test that the correct change was recorded.
        self.assertEqual(len(self.datastore._changes), 1)
        self.assertEqual(self.datastore._changes[0],
                         datastore._Change(datastore.INSERT, 't1', 'r1', {'foo': 42}))

    def test_bad_record_id(self):
        self.table.get('a')  # Shouldn't raise.
        self.assertRaises(ValueError, self.table.get, '@')
        self.table.get_or_insert('a')  # Shouldn't raise.
        self.assertRaises(ValueError, self.table.get_or_insert, '@')

    def test_insert(self):
        r1 = self.table.insert(foo=42)
        r2 = self.table.insert(foo=42)
        self.assertNotEqual(r1.get_id(), r2.get_id())
        self.assertEqual(self.table.get(r1.get_id()), r1)
        self.assertEqual(self.table.get(r2.get_id()), r2)

        # White box test that the correct changes were recorded.
        self.assertEqual(len(self.datastore._changes), 2)
        self.assertEqual(self.datastore._changes[0],
                         datastore._Change(datastore.INSERT, 't1', r1.get_id(), {'foo': 42}))
        self.assertEqual(self.datastore._changes[1],
                         datastore._Change(datastore.INSERT, 't1', r2.get_id(), {'foo': 42}))

    def test_insert_none(self):
        self.assertRaises(TypeError, self.table.insert, foo=None)
        self.assertRaises(TypeError, self.table.get_or_insert, 'r1', foo=None)

    def test_query(self):
        r1 = self.table.get_or_insert('r1', foo=0, baz='')
        r2 = self.table.get_or_insert('r2', foo=0, bar='abc', baz=False)
        r3 = self.table.get_or_insert('r3', bar='abc', baz=True)

        res = self.table.query()
        self.assertEqual(set(r.get_id() for r in res), set(('r1', 'r2', 'r3')))

        res = self.table.query(foo=0)
        self.assertEqual(set(r.get_id() for r in res), set(('r1', 'r2')))

        res = self.table.query(bar='abc')
        self.assertEqual(set(r.get_id() for r in res), set(('r2', 'r3')))

        res = self.table.query(baz=True)
        self.assertEqual(res, set([r3]))

        res = self.table.query(foo=0, bar='abc')
        self.assertEqual(res, set([r2]))

        res = self.table.query(foo=0, baz=True)
        self.assertEqual(res, set())

        res = self.table.query(foo=False)  # False == 0, but shouldn't match.
        self.assertEqual(res, set())

        res = self.table.query(baz=1)  # 1 == True, but shouldn't match.
        self.assertEqual(res, set())

    def test_insert_unicode(self):
        r = self.table.insert(x='x')
        x = r.get('x')
        self.assertEqual(type(x), unicode)

    def test_update_unicode(self):
        r = self.table.insert()
        r.update(y='y')
        y = r.get('y')
        self.assertEqual(type(y), unicode)

    def test_query_unicode(self):
        # Test equivalence of unicode and utf-8-encoded 8-bit string.
        if PY3:
            return
        strings = [u'', u'abc', u'\xff', u'\u1234', u'\U00012345']
        for u in strings:
            b = u.encode('utf-8')
            r = self.table.insert(u=u, b=b)
            self.assertEqual(self.table.query(u=u), set([r]))
            self.assertEqual(self.table.query(b=b), set([r]))
            self.assertEqual(self.table.query(u=b), set([r]))
            self.assertEqual(self.table.query(b=u), set([r]))
            r.delete_record()

    def test_bad_field_name(self):
        # Use **kwds to construct an invalid field name; Python
        # doesn't require the keywords to be valid identifiers.
        self.assertRaises(ValueError, self.table.get_or_insert, 'r1', **{'@': ''})
        self.assertRaises(ValueError, self.table.insert, **{'@': ''})
        self.assertRaises(ValueError, self.table.query, **{'@': ''})


class TestRecord(unittest.TestCase):
    """Tests for Record."""

    def setUp(self):
        self.client = mock.Mock()
        self.client.request.return_value = ('', {}, [])  # Dummy url, params, headers.
        self.manager = datastore.DatastoreManager(self.client)
        self.datastore = datastore.Datastore(self.manager, id='xyzzy', handle='deadbeef')
        self.table = self.datastore.get_table('t1')
        self.record = self.table.get_or_insert('r1', foo=42)
        # Fake commit.
        self.datastore._changes = []
        self.datastore._rev = 1

    def test_repr(self):
        self.assertEqual(repr(self.record), "Record(<t1>, 'r1', {'foo': 42})")

    def test_eq_ne(self):
        r1 = self.table.get('r1')
        r3 = self.table.get_or_insert('r3', foo=42)  # Different record ID.
        r1t2 = self.datastore.get_table('t2').get_or_insert('r1', foo=42)  # Different Table.
        self.assertTrue(self.record == r1)
        self.assertFalse(self.record == r3)
        self.assertFalse(self.record == r1t2)
        self.assertFalse(self.record == 'blah')
        self.assertFalse(self.record != r1)
        self.assertTrue(self.record != r3)
        self.assertTrue(self.record != r1t2)
        self.assertTrue(self.record != 'blah')
        self.assertTrue(self.record != None)

    def test_hash(self):
        r1 = self.table.get('r1')
        r2 = self.table.insert()
        self.assertEqual(hash(r1), hash(self.record))
        self.assertNotEqual(hash(r1), hash(r2))

    def test_is_valid_id(self):
        for id in GOOD_IDS:
            self.assertTrue(datastore.Record.is_valid_id(id), id)
        for id in BAD_IDS:
            self.assertFalse(datastore.Record.is_valid_id(id), id)

    def test_is_valid_field(self):
        for id in GOOD_IDS:
            self.assertTrue(datastore.Record.is_valid_field(id), id)
        for id in BAD_IDS:
            self.assertFalse(datastore.Record.is_valid_field(id), id)

    def test_get_id(self):
        self.assertEqual(self.record.get_id(), 'r1')

    def test_get_table(self):
        self.assertTrue(self.record.get_table() is self.table)

    def test_get(self):
        self.assertEqual(self.record.get('foo'), 42)
        self.assertEqual(self.record.get('bar'), None)

    def test_set(self):
        self.record.set('bar', 'abc')
        self.assertEqual(self.record.get('bar'), 'abc')
        self.assertEqual(len(self.datastore._changes), 1)
        self.assertEqual(self.datastore._changes[0],
                         datastore._Change(datastore.UPDATE, 't1', 'r1',
                                          data={'bar': [datastore.ValuePut, 'abc']},
                                          undo={'bar': None}))

    def test_set_none(self):
        # Set to None should be the same as delete.
        self.record.set('foo', None)
        self.assertTrue(self.record.get('foo') is None)
        self.assertEqual(self.datastore._changes,
                         [datastore._Change(datastore.UPDATE, 't1', 'r1',
                                           data={'foo': [datastore.ValueDelete]},
                                           undo={'foo': 42}),
                          ])
        # Deleting it again is a no-op.
        self.datastore._changes = []
        self.record.set('foo', None)
        self.assertEqual(self.datastore._changes, [])

    def test_delete(self):
        self.record.delete('foo')
        self.assertTrue(self.record.get('foo') is None)
        self.assertEqual(self.datastore._changes,
                         [datastore._Change(datastore.UPDATE, 't1', 'r1',
                                           data={'foo': [datastore.ValueDelete]},
                                           undo={'foo': 42}),
                          ])
        # Deleting it again is a no-op.
        self.datastore._changes = []
        self.record.delete('foo')
        self.assertEqual(self.datastore._changes, [])

    def test_get_fields(self):
        self.assertEqual(self.record.get_fields(), {'foo': 42})
        self.record.update(foo=100, bar='abc')
        self.assertEqual(self.record.get_fields(), {'foo': 100, 'bar': 'abc'})
        self.record.update(foo=None)
        self.assertEqual(self.record.get_fields(), {'bar': 'abc'})

    def test_update(self):
        self.record.update(foo=None, bar='abc')
        self.assertEqual(self.record.get('foo'), None)
        self.assertEqual(self.record.get('bar'), 'abc')
        self.assertEqual(len(self.datastore._changes), 1)
        self.assertEqual(self.datastore._changes[0],
                         datastore._Change(datastore.UPDATE, 't1', 'r1',
                                          data={'foo': [datastore.ValueDelete],
                                                'bar': [datastore.ValuePut, 'abc']},
                                          undo={'foo': 42, 'bar': None}))

    def test_good_types(self):
        self.client.rest_client.POST.return_value = {'rev': 2}
        inf = 1e1000
        neginf = -inf
        nan = inf/inf
        blob = datastore.Bytes(b'xxx\0\xff')
        date = datastore.Date(1234567890.123456)
        r = self.table.insert(f_true=True,
                              f_false=False,
                              f_int=42,
                              f_long=1000000000000000000,
                              f_float=3.14,
                              f_inf=inf,
                              f_negfinf=neginf,
                              f_nan=nan,
                              f_str='abc',
                              f_unicode=u'\u1234',
                              f_blob=blob,
                              f_date=date,
                              )
        self.record.update(f_true=True,
                           f_false=False,
                           f_int=42,
                           f_long=1000000000000000000,
                           f_float=3.14,
                           f_inf=inf,
                           f_negfinf=neginf,
                           f_nan=nan,
                           f_str='abc',
                           f_unicode=u'\u1234',
                           f_blob=blob,
                           f_date=date,
                           )
        self.datastore.commit()

    def test_bad_types(self):
        for bad in [{}, set(), object(), Exception, Ellipsis, NotImplemented, lambda: None]:
            self.assertRaises(TypeError, self.table.insert, f_bad=bad)
            self.assertRaises(TypeError, self.record.update, f_bad=bad)

    def test_delete_record(self):
        self.assertFalse(self.record.is_deleted())
        self.record.delete_record()
        self.assertTrue(self.record.is_deleted())
        self.assertEqual(self.record.get('foo'), None)
        self.assertEqual(self.record.get_fields(), {})
        self.assertRaises(datastore.DatastoreError, self.record.set, 'foo', 1)
        self.assertRaises(datastore.DatastoreError, self.record.get_or_create_list, 'foo')
        self.assertEqual(repr(self.record), "Record(<t1>, 'r1', <deleted>)")
        self.assertEqual(self.datastore._changes,
                         [datastore._Change(datastore.DELETE, 't1', 'r1', None, {'foo': 42}),
                          ])
        # Deleting it again is a no-op.
        self.datastore._changes = []
        self.record.delete_record()
        self.assertEqual(self.datastore._changes, [])

    def test_delete_record_rollback(self):
        self.assertFalse(self.record.is_deleted())
        self.record.delete_record()
        self.assertTrue(self.record.is_deleted())
        self.datastore.rollback()
        self.assertFalse(self.record.is_deleted())  # Hah!

    def test_delete_record_alias(self):
        r1 = self.record
        r2 = self.table.get_or_insert('r1', foo=42)
        r1.delete_record()
        self.assertRaises(datastore.DatastoreError, r1.update, foo=42)
        self.assertRaises(datastore.DatastoreError, r2.update, foo=42)

    def test_has(self):
        self.assertTrue(self.record.has('foo'))
        self.assertFalse(self.record.has('bar'))

    def test_bad_field_name(self):
        self.assertRaises(ValueError, self.record.get, '@')
        self.assertRaises(ValueError, self.record.set, '@', '')
        self.assertRaises(ValueError, self.record.delete, '@')
        self.assertRaises(ValueError, self.record.update, **{'@': ''})
        self.assertRaises(ValueError, self.record.get_or_create_list, '@')
        self.assertRaises(ValueError, self.record.has, '@')


class TestValuesJson(unittest.TestCase):
    """Tests for value JSON loading/dumping."""

    def test_to_json(self):
        inf = 1e1000
        neginf = -inf
        nan = inf/inf
        self.assertEqual(datastore._value_to_json(inf), {'N': '+inf'})
        self.assertEqual(datastore._value_to_json(neginf), {'N': '-inf'})
        self.assertEqual(datastore._value_to_json(nan), {'N': 'nan'})

    def test_from_json(self):
        inf = 1e1000
        neginf = -inf
        self.assertEqual(datastore._value_from_json({'N': '+inf'}), inf)
        self.assertEqual(datastore._value_from_json({'N': '-inf'}), neginf)
        nan = datastore._value_from_json({'N': 'nan'})
        self.assertTrue(math.isnan(nan))


class TestDate(unittest.TestCase):
    """Tests for Date."""

    def setUp(self):
        # The Epoch is 1/1/1970 UTC.
        # The first test date is Jan 1, 1971, 12:34:56, 789 msec.
        # The second test date is Jan 2, 1971, 12:34:56, 789 msec.
        self.ts_one = 365 * 24 * 3600 + 12*3600 + 34*60 + 56 + 0.789654
        self.ts_two = self.ts_one + 24 * 3600 + 3661.101010
        self.d_one = datastore.Date(self.ts_one)
        self.d_two = datastore.Date(self.ts_two)
        self.dt_one = datetime.datetime(1971, 1, 1, 12, 34, 56, 789000)
        self.dt_two = datetime.datetime(1971, 1, 2, 13, 35, 57, 890000)

    def test_init(self):
        a = self.d_one
        a_i = datastore.Date(int(self.ts_one))
        a_l = datastore.Date(long(self.ts_one))
        self.assertEqual(int(a), int(a_i))
        self.assertEqual(long(a), long(a_l))
        self.assertEqual(a_i, a_l)
        self.assertEqual(float(a_i), float(a_l))
        self.assertEqual(int(a), int(a_i))
        self.assertEqual(int(a), int(a_l))
        self.assertEqual(long(a), long(a_i))
        self.assertEqual(long(a), long(a_l))
        b = datastore.Date(float(self.ts_two))
        self.assertNotEqual(a, b)

    def test_init_errors(self):
        self.assertRaises(TypeError, datastore.Date, 'abc')
        self.assertRaises(TypeError, datastore.Date, {})

    def test_init_default(self):
        a = datastore.Date(time.time())
        b = datastore.Date()
        c = datastore.Date(time.time())
        self.assertTrue(a <= b <= c, 'not %s <= %s <= %s' % (a, b, c))

    def test_repr(self):
        self.assertEqual(repr(self.d_one), 'Date<1971-01-01 12:34:56.789 UTC>')
        self.assertEqual(repr(self.d_two), 'Date<1971-01-02 13:35:57.890 UTC>')

    def test_comparisons(self):
        self.assertFalse(self.d_one == 'abc')
        self.assertFalse(self.d_one == self.d_two)
        self.assertTrue(self.d_one != 'abc')
        self.assertTrue(self.d_one != self.d_two)
        self.assertTrue(self.d_one < self.d_two)
        self.assertTrue(self.d_one <= self.d_two)
        self.assertFalse(self.d_one > self.d_two)
        self.assertFalse(self.d_one >= self.d_two)
        self.assertTrue(self.d_one.__lt__('abc') is NotImplemented)
        self.assertTrue(self.d_one.__le__('abc') is NotImplemented)
        self.assertTrue(self.d_one.__gt__('abc') is NotImplemented)
        self.assertTrue(self.d_one.__ge__('abc') is NotImplemented)

    def test_to_datetime_utc(self):
        self.assertEqual(self.d_one.to_datetime_utc(), self.dt_one)

    def test_to_datetime_local(self):
        # This test will fail in the Southern hemisphere in a country with DST.
        self.assertEqual(self.d_one.to_datetime_local(),
                         self.dt_one - datetime.timedelta(seconds=time.timezone))

    def test_from_datetime_utc(self):
        self.assertEqual(self.d_one, datastore.Date.from_datetime_utc(self.dt_one))

    def test_from_datetime_utc_error(self):
        bad = self.dt_one.replace(tzinfo=datetime.tzinfo())
        self.assertRaises(TypeError, datastore.Date.from_datetime_utc, bad)

    def test_from_datetime_local(self):
        # This test will fail in the Southern hemisphere in a country with DST.
        self.assertEqual(self.d_one,
                         datastore.Date.from_datetime_local(
                             self.dt_one - datetime.timedelta(seconds=time.timezone)))

    def test_from_datetime_local_error(self):
        bad = self.dt_one.replace(tzinfo=datetime.tzinfo())
        self.assertRaises(TypeError, datastore.Date.from_datetime_local, bad)

    def test_to_json(self):
        j = datastore._value_to_json(self.d_one)
        self.assertEqual(j, {'T': str(int(self.ts_one * 1000))})

    def test_from_json(self):
        j = {'T': str(int(self.ts_one * 1000))}
        self.assertEqual(datastore._value_from_json(j), self.d_one)
        j = {'T': '123456789012'}  # Exhibits a weird rounding error.
        self.assertEqual(datastore._value_from_json(j), datastore.Date(123456789.012))

    def test_date_fields(self):
        # Set up mock datastore and table.
        self.client = mock.Mock()
        self.client.request.return_value = ('', {}, [])  # Dummy url, params, headers.
        self.manager = datastore.DatastoreManager(self.client)
        self.datastore = datastore.Datastore(self.manager, id='xyzzy', handle='deadbeef')
        self.table = self.datastore.get_table('t1')
        # Create a record with a Date field.
        record = self.table.insert(one=self.d_one, two=self.d_two)
        # Get stuff out.
        one = record.get('one')
        two = record.get('two')
        self.assertEqual(one, self.d_one)
        self.assertEqual(two, self.d_two)


class TestBytes(unittest.TestCase):
    """Tests for Bytes."""

    def test_init(self):
        a = datastore.Bytes(b'\xffoo')
        b = datastore.Bytes(buffer(b'bu\xffer'))
        if not PY3:
            c = datastore.Bytes(array.array('c', b'\0\1\2'))
        d = datastore.Bytes(array.array('b', b'\3\4\5'))
        e = datastore.Bytes(array.array('B', b'\6\7\10'))
        self.assertRaises(Exception, datastore.Bytes, array.array('i', [1, 2, 3]))
        self.assertRaises(Exception, datastore.Bytes, u'hola')
        self.assertRaises(Exception, datastore.Bytes, 42)

    def test_repr(self):
        a = datastore.Bytes(b'foo')
        if PY3:
            self.assertEqual(repr(a), "Bytes(b'foo')")
        else:
            self.assertEqual(repr(a), "Bytes('foo')")

    def test_unicode(self):
        a = datastore.Bytes(b'foo')
        if not PY3:
            self.assertEqual(unicode(a), repr(a))

    def test_str(self):
        a = datastore.Bytes(b'foo')
        b = bytes(a)
        self.assertTrue(isinstance(b, bytes))
        self.assertEqual(b, b'foo')

    def test_len(self):
        self.assertEqual(len(datastore.Bytes(b'foo')), 3)
        self.assertEqual(len(datastore.Bytes(b'\xffoo')), 3)

    def test_comparisons(self):
        foo = datastore.Bytes(b'foo')
        foo2 = datastore.Bytes(b'foo')
        bar = datastore.Bytes(b'bar')

        self.assertTrue(foo == foo2)
        self.assertFalse(foo == bar)
        self.assertTrue(foo == b'foo')
        self.assertFalse(foo == b'bar')

        self.assertFalse(foo != foo2)
        self.assertTrue(foo != bar)
        self.assertFalse(foo != b'foo')
        self.assertTrue(foo != b'bar')

        self.assertFalse(foo < foo2)
        self.assertFalse(foo < bar)
        self.assertFalse(foo < b'foo')
        self.assertFalse(foo < b'bar')

        self.assertTrue(foo <= foo2)
        self.assertFalse(foo <= bar)
        self.assertTrue(foo <= b'foo')
        self.assertFalse(foo <= b'bar')

        self.assertFalse(foo > foo2)
        self.assertTrue(foo > bar)
        self.assertFalse(foo > b'foo')
        self.assertTrue(foo > b'bar')

        self.assertTrue(foo >= foo2)
        self.assertTrue(foo >= bar)
        self.assertTrue(foo >= b'foo')
        self.assertTrue(foo >= b'bar')

        self.assertTrue(foo.__eq__(u'foo') is NotImplemented)
        self.assertTrue(foo.__ne__(u'foo') is NotImplemented)
        self.assertTrue(foo.__lt__(u'foo') is NotImplemented)
        self.assertTrue(foo.__le__(u'foo') is NotImplemented)
        self.assertTrue(foo.__gt__(u'foo') is NotImplemented)
        self.assertTrue(foo.__ge__(u'foo') is NotImplemented)

    def test_to_json(self):
        foo = datastore.Bytes(b'foo')
        j = datastore._value_to_json(foo)
        self.assertEqual(j, {'B': 'Zm9v'})

    def test_from_json(self):
        foo = datastore.Bytes(b'foo')
        j = {'B': 'Zm9v'}
        self.assertEqual(datastore._value_from_json(j), foo)


class TestList(unittest.TestCase):
    """Tests for List and list fields.

    This tests both fields whose value is a list (represented
    internally as a tuple) as well as the behavior of the List wrapper
    class.
    """

    def setUp(self):
        self.client = mock.Mock()
        self.client.request.return_value = ('', {}, [])  # Dummy url, params, headers.
        self.manager = datastore.DatastoreManager(self.client)
        self.datastore = datastore.Datastore(self.manager, id='xyzzy', handle='deadbeef')
        self.table = self.datastore.get_table('t1')

    def test_insert(self):
        r1 = self.table.insert(foo=[1, 2, 3], bar=['a', 'b', 'c'])
        self.assertEqual(r1.get('foo'), (1, 2, 3))
        self.assertEqual(r1.get('bar'), ('a', 'b', 'c'))

        # White box test that the correct changes were recorded.
        self.assertEqual(len(self.datastore._changes), 1)
        self.assertEqual(self.datastore._changes[0],
                         datastore._Change(datastore.INSERT, 't1', r1.get_id(),
                                          {'foo': (1, 2, 3), 'bar': ('a', 'b', 'c')}))

    def test_update(self):
        r1 = self.table.insert(foo=[1, 2, 3])
        self.datastore._changes = []  # Fake commit.
        r1.update(foo=[4, 5, 6], bar=['a', 'b', 'c'])
        self.assertEqual(r1.get('foo'), (4, 5, 6))
        self.assertEqual(r1.get('bar'), ('a', 'b', 'c'))

        # White box test that the correct changes were recorded.
        self.assertEqual(len(self.datastore._changes), 1)
        self.assertEqual(self.datastore._changes[0],
                         datastore._Change(datastore.UPDATE, 't1', r1.get_id(),
                                          {'foo': [datastore.ValuePut, (4, 5, 6)],
                                           'bar': [datastore.ValuePut, ('a', 'b', 'c')]},
                                          {'foo': (1, 2, 3), 'bar': None}))

    def test_delete(self):
        r1 = self.table.insert(foo=(1, 2, 3))
        self.datastore._changes = []  # Fake commit.
        r1.update(foo=None)
        self.assertEqual(r1.get('foo'), None)

        # White box test that the correct changes were recorded.
        self.assertEqual(len(self.datastore._changes), 1)
        self.assertEqual(self.datastore._changes[0],
                         datastore._Change(datastore.UPDATE, 't1', r1.get_id(),
                                          {'foo': [datastore.ValueDelete]},
                                          {'foo': (1, 2, 3)}))

    def test_list_wrappers(self):
        r1 = self.table.insert(foo=(1, 2, 3), bar=(1, 2, 3))
        foo = r1.get('foo')
        bar = r1.get('bar')
        self.assertTrue(isinstance(foo, datastore.List))
        self.assertTrue(isinstance(bar, datastore.List))
        self.assertEqual(foo.get_field(), 'foo')
        self.assertEqual(foo.get_record(), r1)
        self.assertEqual(foo, (1, 2, 3))
        self.assertEqual(bar, [1, 2, 3])
        self.assertEqual(foo, bar)
        foo.append(4)
        self.assertEqual(foo, (1, 2, 3, 4))
        self.assertNotEqual(foo, bar)

    def test_list_ops(self):
        r1 = self.table.get_or_insert('r1', foo=(1, 2, 3))
        foo = r1.get('foo')
        # Test that we get a List back.
        self.assertTrue(isinstance(foo, datastore.List))
        # Test some special methods.
        self.assertEqual(repr(foo), "List(<r1>, 'foo')")
        self.assertEqual(len(foo), 3)
        self.assertEqual(tuple(iter(foo)), (1, 2, 3))
        # Test get and set item operations.
        self.assertEqual(foo[0], 1)
        self.assertEqual(foo[-1], 3)
        foo[0] = 'a'
        self.assertEqual(foo, ['a', 2, 3])
        foo[-2] = 'b'
        foo[-1] = 'c'
        self.assertEqual(foo, ['a', 'b', 'c'])
        del foo[0]
        self.assertEqual(foo, ['b', 'c'])
        del foo[-1]
        self.assertEqual(foo, ['b'])
        # Test standard mutable sequence methods.
        foo.insert(1, 'c')
        self.assertEqual(foo, ['b', 'c'])
        foo.insert(-2, 'a')
        self.assertEqual(foo, ['a', 'b', 'c'])
        foo.insert(-100, 'x')
        self.assertEqual(foo, ['x', 'a', 'b', 'c'])
        foo.insert(100, 'y')
        self.assertEqual(foo, ['x', 'a', 'b', 'c', 'y'])
        del foo[0], foo[-1]  # Restore ['a', 'b', 'c'].
        foo.append('d')
        self.assertEqual(foo, ['a', 'b', 'c', 'd'])
        # Test move method.
        foo.move(0, 2)
        self.assertEqual(foo, ['b', 'c', 'a', 'd'])
        foo.move(2, 0)
        self.assertEqual(foo, ['a', 'b', 'c', 'd'])
        foo.move(-1, -2)
        self.assertEqual(foo, ['a', 'b', 'd', 'c'])
        foo.move(-4, 3)
        self.assertEqual(foo, ['b', 'd', 'c', 'a'])

    def test_list_ops_index_ranges(self):
        # Test extreme ends of index values.
        # This includes checking that the correct changes were
        # recorded for negative or truncated indexes.
        r1 = self.table.get_or_insert('r1', foo=('a', 'b', 'c', 'd'))
        foo = r1.get('foo')
        # __getitem__
        self.assertEqual(foo[0], 'a')
        self.assertEqual(foo[3], 'd')
        self.assertEqual(foo[-1], 'd')
        self.assertEqual(foo[-4], 'a')
        self.assertRaises(IndexError, foo.__getitem__, 4)
        self.assertRaises(IndexError, foo.__getitem__, -5)
        # __setitem__
        self.datastore._changes = []
        c = ChangesBuilder()
        c.list_op('Put', 'r1', 'foo', 0, 'A', old=tuple(foo))
        foo[0] = 'A'
        c.list_op('Put', 'r1', 'foo', 3, 'D', old=tuple(foo))
        foo[3] = 'D'
        self.assertEqual(list(foo), ['A', 'b', 'c', 'D'])
        c.list_op('Put', 'r1', 'foo', 3, 'dd', old=tuple(foo))
        foo[-1] = 'dd'
        c.list_op('Put', 'r1', 'foo', 0, 'aa', old=tuple(foo))
        foo[-4] = 'aa'
        self.assertEqual(list(foo), ['aa', 'b', 'c', 'dd'])
        self.assertRaises(IndexError, foo.__setitem__, 4, 'x')
        self.assertRaises(IndexError, foo.__setitem__, -5, 'x')
        self.assertEqual(self.datastore._changes, c.changes)
        # __delitem__
        self.datastore._changes = []
        c = ChangesBuilder()
        self.assertRaises(IndexError, foo.__delitem__, 4)
        self.assertRaises(IndexError, foo.__delitem__, -5)
        c.list_op('Delete', 'r1', 'foo', 0, old=tuple(foo))
        del foo[0]
        c.list_op('Delete', 'r1', 'foo', 2, old=tuple(foo))
        del foo[2]
        c.list_op('Delete', 'r1', 'foo', 0, old=tuple(foo))
        del foo[-2]
        c.list_op('Delete', 'r1', 'foo', 0, old=tuple(foo))
        del foo[-1]
        self.assertEqual(list(foo), [])
        self.assertEqual(self.datastore._changes, c.changes)
        # insert()
        self.datastore._changes = []
        c = ChangesBuilder()
        c.list_op('Insert', 'r1', 'foo', 0, 'a', old=tuple(foo))
        foo.insert(-100, 'a')
        c.list_op('Insert', 'r1', 'foo', 1, 'b', old=tuple(foo))
        foo.insert(100, 'b')
        self.assertEqual(list(foo), ['a', 'b'])
        self.assertEqual(self.datastore._changes, c.changes)
        # append()
        self.datastore._changes = []
        c = ChangesBuilder()
        c.list_op('Insert', 'r1', 'foo', 2, 'c', old=tuple(foo))
        foo.append('c')
        c.list_op('Insert', 'r1', 'foo', 3, 'd', old=tuple(foo))
        foo.append('d')
        self.assertEqual(list(foo), ['a', 'b', 'c', 'd'])
        self.assertEqual(self.datastore._changes, c.changes)
        # move()
        self.datastore._changes = []
        c = ChangesBuilder()
        c.list_op('Move', 'r1', 'foo', 0, newindex=3, old=tuple(foo))
        foo.move(0, 3)
        self.assertEqual(list(foo), ['b', 'c', 'd', 'a'])
        c.list_op('Move', 'r1', 'foo', 3, newindex=0, old=tuple(foo))
        foo.move(-1, -4)
        self.assertEqual(list(foo), ['a', 'b', 'c', 'd'])
        self.assertRaises(IndexError, foo.move, 0, 4)
        self.assertRaises(IndexError, foo.move, 4, 0)
        self.assertRaises(IndexError, foo.move, 0, -5)
        self.assertRaises(IndexError, foo.move, -5, 0)
        self.assertEqual(self.datastore._changes, c.changes)

    def test_other_list_ops(self):
        r1 = self.table.get_or_insert('r1', foo=(1, 2, 3))
        foo = r1.get('foo')
        self.assertTrue(isinstance(foo, datastore.List))
        # Getting slices works!
        self.assertEqual(foo[:], (1, 2, 3))
        self.assertEqual(foo[1:], (2, 3))
        self.assertEqual(foo[:2], (1, 2))
        self.assertEqual(foo[1:-1], (2,))
        # Setting or deleting slices is not supported.
        self.assertRaises(TypeError, foo.__setitem__, slice(None), ())
        self.assertRaises(TypeError, foo.__delitem__, slice(None))
        # But extend() is.
        foo.extend((4, 5))
        self.assertEqual(foo, (1, 2, 3, 4, 5))
        # in.
        self.assertTrue(2 in foo)
        self.assertFalse(10 in foo)
        # reverse().
        foo.reverse()
        self.assertEqual(foo, (5, 4, 3, 2, 1))
        # pop().
        x = foo.pop(0)
        self.assertEqual(x, 5)
        self.assertEqual(foo, (4, 3, 2, 1))
        # index().
        self.assertEqual(foo.index(1), 3)
        # remove().
        foo.remove(2)
        self.assertEqual(foo, (4, 3, 1))
        # +=.
        foo += (99, 100)
        self.assertEqual(foo, (4, 3, 1, 99, 100))

    def test_comparisons(self):
        r1 = self.table.get_or_insert('r1', foo=(1, 2, 3), bar=(1, 2, 3), baz=(1, 2, 4))
        foo = r1.get('foo')
        bar = r1.get('bar')
        baz = r1.get('baz')
        # Compare two Lists.
        self.assertTrue(foo == bar)
        self.assertFalse(foo != bar)
        self.assertTrue(foo < baz)
        self.assertTrue(foo <= baz)
        self.assertFalse(foo > baz)
        self.assertFalse(foo >= baz)
        # Compare a List and a tuple.
        self.assertTrue(foo == (1, 2, 3))
        self.assertFalse(foo != (1, 2, 3))
        self.assertTrue(foo < (1, 2, 4))
        self.assertTrue(foo <= (1, 2, 4))
        self.assertFalse(foo > (1, 2, 4))
        self.assertFalse(foo >= (1, 2, 4))
        # Compare a List and a list.
        self.assertTrue(foo == [1, 2, 3])
        self.assertFalse(foo != [1, 2, 3])
        self.assertTrue(foo < [1, 2, 4])
        self.assertTrue(foo <= [1, 2, 4])
        self.assertFalse(foo > [1, 2, 4])
        self.assertFalse(foo >= [1, 2, 4])
        # Compare a List and something bad.
        self.assertFalse(foo == array.array('i', [1, 2, 3]))
        self.assertTrue(foo != array.array('i', [1, 2, 3]))
        self.assertTrue(foo.__lt__('\1\2\3') is NotImplemented)
        self.assertTrue(foo.__le__('\1\2\3') is NotImplemented)
        self.assertTrue(foo.__gt__('\1\2\3') is NotImplemented)
        self.assertTrue(foo.__ge__('\1\2\3') is NotImplemented)

    def test_good_types(self):
        r1 = self.table.get_or_insert('r1')
        foo = r1.get_or_create_list('foo')
        inf = 1e1000
        neginf = -inf
        nan = inf/inf
        blob = datastore.Bytes(b'xxx\0\xff')
        date = datastore.Date(1234567890.123456)
        values = (True, False,
                  42, 1000000000000000000,
                  3.14, inf, neginf, nan,
                  'abc', u'\u1234',
                  blob,
                  date,
                  )
        foo.append('dummy')
        for v in values:
            foo[0] = v
        del foo[0]
        for v in values:
            foo.append(v)
        foo.append('dummy')
        for v in values:
            foo.insert(-1, v)
        del foo[-1]
        self.assertEqual(foo, values + values)

    def test_bad_types(self):
        r1 = self.table.get_or_insert('r1')
        foo = r1.get_or_create_list('foo')
        foo.append('dummy')
        for bad in [{}, set(), object(), Exception, Ellipsis, NotImplemented, lambda: None]:
            self.assertRaises(TypeError, foo.append, bad)
            self.assertRaises(TypeError, foo.insert, 0, bad)
            self.assertRaises(TypeError, foo.__setitem__, 0, bad)

    def test_list_unicode(self):
        r1 = self.table.get_or_insert('r1')
        r1.set('foo', ['y'])
        foo = r1.get('foo')
        foo.append('z')
        foo.insert(0, 'x')
        foo = r1.get('foo')
        self.assertEqual(foo, ('x', 'y', 'z'))
        for x in foo:
            self.assertEqual(type(x), unicode)

    def test_get_or_create_list(self):
        r1 = self.table.get_or_insert('r1', bar=42)
        foo = r1.get_or_create_list('foo')
        self.assertTrue(isinstance(foo, datastore.List))
        foo.append(42)
        foo2 = r1.get_or_create_list('foo')
        self.assertTrue(isinstance(foo2, datastore.List))
        self.assertEqual(foo2, [42])
        self.assertRaises(TypeError, r1.get_or_create_list, 'bar')

    def test_reference_deleted_rec(self):
        r1 = self.table.get_or_insert('r1')
        foo = r1.get_or_create_list('foo')
        self.assertEqual(len(foo), 0)
        r1.delete_record()
        self.assertRaises(TypeError, len, foo)

    def test_reference_non_list(self):
        r1 = self.table.get_or_insert('r1')
        foo = r1.get_or_create_list('foo')
        self.assertEqual(len(foo), 0)
        r1.set('foo', 42)
        self.assertRaises(TypeError, len, foo)

    def test_aliasing(self):
        r1 = self.table.get_or_insert('r1', foo=(1, 2, 3))
        foo = r1.get('foo')
        self.assertTrue(isinstance(foo, datastore.List))
        r1.set('bar', foo)
        bar = r1.get('bar')
        self.assertEqual(bar, (1, 2, 3))
        foo.append(99)
        self.assertEqual(bar, (1, 2, 3))

    def test_incoming_ops(self):
        r1 = self.table.get_or_insert('r1', bar=['x'], baz=[1], bla=[99], bah=['a', 'b', 'c'])
        self.datastore._changes = []  # Fake commit.
        self.datastore._rev = 1

        # setup mocks
        c = ChangesBuilder()
        c.list_op('Create', 'r1', 'foo')
        c.list_op('Insert', 'r1', 'bar', 1, 'abc')
        c.list_op('Put', 'r1', 'baz', 0, 42)
        c.list_op('Delete', 'r1', 'bla', 0)
        c.list_op('Move', 'r1', 'bah', 0, newindex=2)
        deltas = [{'rev': 1, 'changes': [ch.to_json() for ch in c.changes]}]
        self.client.rest_client.GET.return_value = {'deltas': deltas}

        # invoke code
        out = self.datastore.load_deltas()

        # check code
        t1 = self.datastore.get_table('t1')
        self.assertEqual(out, {'t1': set([datastore.Record(t1, 'r1')])})
        self.assertEqual(r1.get('foo'), ())
        self.assertEqual(r1.get('bar'), ('x', 'abc'))
        self.assertEqual(r1.get('baz'), (42,))
        self.assertEqual(r1.get('bla'), ())
        self.assertEqual(r1.get('bah'), ('b', 'c', 'a'))

    def test_outgoing_ops(self):
        r1 = self.table.get_or_insert('r1', bar=['x'], baz=[1], bla=[99], bah=['a', 'b', 'c'])
        self.datastore._changes = []  # Fake commit.
        self.datastore._rev = 1

        self.assertEqual(r1.get('foo'), None)
        foo = r1.get_or_create_list('foo')
        self.assertTrue(isinstance(foo, datastore.List))
        self.assertEqual(foo, [])
        self.assertEqual(r1.get('foo'), foo)
        foo2 = r1.get_or_create_list('foo')
        self.assertEqual(foo2, foo)

        bar = r1.get('bar')
        self.assertEqual(bar, ['x'])
        bar.insert(1, 'abc')
        self.assertEqual(bar, ['x', 'abc'])

        baz = r1.get('baz')
        self.assertEqual(baz, [1])
        baz[0] = 42
        self.assertEqual(baz, [42])

        bla = r1.get('bla')
        self.assertEqual(bla, [99])
        del bla[0]
        self.assertEqual(bla, [])

        bah = r1.get('bah')
        self.assertEqual(bah, ['a', 'b', 'c'])
        bah.move(0, 2)
        self.assertEqual(bah, ['b', 'c', 'a'])

        c = ChangesBuilder()
        c.list_op('Create', 'r1', 'foo')
        c.list_op('Insert', 'r1', 'bar', 1, 'abc', old=('x',))
        c.list_op('Put', 'r1', 'baz', 0, 42, old=(1,))
        c.list_op('Delete', 'r1', 'bla', 0, old=(99,))
        c.list_op('Move', 'r1', 'bah', 0, newindex=2, old=('a', 'b', 'c'))

        self.assertEqual(self.datastore._changes, c.changes)

        # Now verify that commit() handles all this correctly.

        # setup mocks
        self.client.rest_client.POST.return_value = {'rev': 2}

        # invoke code
        self.datastore.commit()

        # check code
        self.assertEqual(self.datastore._rev, 2)
        self.assertEqual(self.datastore._changes, [])

        # Pick apart request call args.  This time we just verify that
        # the encoded JSON can be decoded back into the original
        # Change (less undo info).
        args, kwargs = self.client.request.call_args
        path, params = args
        assertRegexpMatches(path, '^/.*/put_delta$')
        self.assertEqual(params['handle'], 'deadbeef')
        self.assertEqual(params['rev'], '1')
        raw_changes = json.loads(params['changes'])
        changes = [datastore._Change.from_json(rc) for rc in raw_changes]
        expected = [ch.without_undo() for ch in changes]
        self.assertEqual(changes, expected)


class TestChange(unittest.TestCase):
    """Tests for Changes."""

    def test_init_repr_invert_insert(self):
        ch = datastore._Change(datastore.INSERT, 't1', 'r1', {'f1': 'v1'})
        self.assertEqual(ch.op, datastore.INSERT)
        self.assertEqual(ch.tid, 't1')
        self.assertEqual(ch.recordid, 'r1')
        self.assertEqual(ch.data, {'f1': 'v1'})
        self.assertEqual(ch.undo, None)

        self.assertEqual(repr(ch), "_Change('I', 't1', 'r1', {'f1': 'v1'})")

        opposite = datastore._Change(datastore.DELETE, 't1', 'r1', None, {'f1': 'v1'})
        self.assertEqual(ch.invert(), opposite)


    def test_init_repr_update(self):
        ch = datastore._Change(datastore.UPDATE, 't1', 'r1',
                              {'f1': [datastore.ValuePut, 'v2']},
                              {'f1': 'v1'})
        self.assertEqual(ch.op, datastore.UPDATE)
        self.assertEqual(ch.tid, 't1')
        self.assertEqual(ch.recordid, 'r1')
        self.assertEqual(ch.data, {'f1': [datastore.ValuePut, 'v2']})
        self.assertEqual(ch.undo, {'f1': 'v1'})

        self.assertEqual(repr(ch), "_Change('U', 't1', 'r1', {'f1': ['P', 'v2']}, {'f1': 'v1'})")
        # See below for tests for inverting UPDATE.

    def test_init_repr_invert_delete(self):
        ch = datastore._Change(datastore.DELETE, 't1', 'r1', None, {'f1': 'v2'})
        self.assertEqual(ch.op, datastore.DELETE)
        self.assertEqual(ch.tid, 't1')
        self.assertEqual(ch.recordid, 'r1')
        self.assertEqual(ch.data, None)
        self.assertEqual(ch.undo, {'f1': 'v2'})

        self.assertEqual(repr(ch), "_Change('D', 't1', 'r1', None, {'f1': 'v2'})")

        opposite = datastore._Change(datastore.INSERT, 't1', 'r1', {'f1': 'v2'})
        self.assertEqual(ch.invert(), opposite)

    def test_eq_ne(self):
        ch1 = datastore._Change(datastore.DELETE, 't1', 'r1', None, {'f1': 'v2'})
        ch2 = datastore._Change(datastore.DELETE, 't1', 'r1', None, {'f1': 'v2'})
        ch3 = datastore._Change(datastore.DELETE, 't1', 'r1', None, {})
        self.assertEqual(ch1, ch2)
        self.assertFalse(ch1 == 'haha')
        self.assertNotEqual(ch1, ch3)
        self.assertTrue(ch1 != 'haha')

    def test_invert_update_add_field(self):
        ch = datastore._Change(datastore.UPDATE, 't1', 'r1',
                              {'f1': [datastore.ValuePut, 'v1']},
                              {'f1': None})
        opposite = datastore._Change(datastore.UPDATE, 't1', 'r1',
                              {'f1': [datastore.ValueDelete]},
                              {'f1': 'v1'})
        self.assertEqual(ch.invert(), opposite)
        self.assertEqual(opposite.invert(), ch)

    def test_invert_update_change_field(self):
        ch = datastore._Change(datastore.UPDATE, 't1', 'r1',
                              {'f1': [datastore.ValuePut, 'v2']},
                              {'f1': 'v1'})
        opposite = datastore._Change(datastore.UPDATE, 't1', 'r1',
                              {'f1': [datastore.ValuePut, 'v1']},
                              {'f1': 'v2'})
        self.assertEqual(ch.invert(), opposite)
        self.assertEqual(opposite.invert(), ch)

    def test_invert_update_delete_field(self):
        ch = datastore._Change(datastore.UPDATE, 't1', 'r1',
                              {'f1': [datastore.ValueDelete]},
                              {'f1': 'v2'})
        opposite = datastore._Change(datastore.UPDATE, 't1', 'r1',
                              {'f1': [datastore.ValuePut, 'v2']},
                              {'f1': None})
        self.assertEqual(ch.invert(), opposite)
        self.assertEqual(opposite.invert(), ch)

    def test_invert_update_list_ops(self):
        # List of (original data, original undo, opposite data, opposite undo).
        samples = [
            ([datastore.ListPut, 1, 'x'], ('a', 'b', 'c'),
             [datastore.ListPut, 1, 'b'], ('a', 'x', 'c')),
            ([datastore.ListInsert, 1, 'x'], ('a', 'b', 'c'),
             [datastore.ListDelete, 1], ('a', 'x', 'b', 'c')),
            ([datastore.ListDelete, 1], ('a', 'b', 'c'),
             [datastore.ListInsert, 1, 'b'], ('a', 'c')),
            ([datastore.ListMove, 1, 2], ('a', 'b', 'c'),
             [datastore.ListMove, 2, 1], ('a', 'c', 'b')),
            ([datastore.ListCreate], None,
            [datastore.ValueDelete], ()),
            ]
        for chdata, chundo, oppdata, oppundo in samples:
            ch = datastore._Change(datastore.UPDATE, 't1', 'r1', {'f1': chdata}, {'f1': chundo})
            opp = datastore._Change(datastore.UPDATE, 't1', 'r1', {'f1': oppdata}, {'f1': oppundo})
            self.assertEqual(ch.invert(), opp)
            if chdata[0] != datastore.ListCreate:  # ListCreate is different.
                self.assertEqual(opp.invert(), ch)


class TestSize(unittest.TestCase):
    """Tests for size accessors."""

    BASE_FIELD_SIZE = datastore.Record.BASE_FIELD_SIZE
    BASE_ITEM_SIZE = datastore.List.BASE_ITEM_SIZE
    BASE_CHANGE_SIZE = datastore.Datastore.BASE_CHANGE_SIZE

    def setUp(self):
        self.client = mock.Mock()
        self.client.request.return_value = ('', {}, [])  # Dummy url, params, headers.
        self.manager = datastore.DatastoreManager(self.client)
        self.datastore = datastore.Datastore(self.manager, id='xyzzy', handle='deadbeef')
        self.table = self.datastore.get_table('t1')


    def _assert_sizes(self, records, change_sizes):
        """Assert our datastore and each record have the expected size.

        records: sequence of zero or more tuples [(Record, expected size of values)]
        change_sizes: sequence of zero or more int change sizes
        """
        total_size = datastore.Datastore.BASE_DATASTORE_SIZE
        for (record, expected_value_size) in records:
            expected_record_size = datastore.Record.BASE_RECORD_SIZE + expected_value_size
            self.assertEquals(record.get_size(), expected_record_size,
                              'Size mismatch for %r with size %d != %d' % (record,
                                                                           record.get_size(),
                                                                           expected_record_size))
            total_size += expected_record_size

        self.assertEquals(self.datastore.get_record_count(), len(records))
        self.assertEquals(self.datastore.get_size(), total_size)
        if change_sizes:
            self.assertEquals(self.datastore.get_pending_changes_size(),
                              self.datastore.BASE_DELTA_SIZE +
                              sum((self.BASE_CHANGE_SIZE + change_size)
                                  for change_size in change_sizes))
        else:
            self.assertEquals(self.datastore.get_pending_changes_size(), 0)

    def test_compute_atom_size_edgecases(self):
        self.assertEquals(datastore._compute_atom_size(None), 0)
        self.assertRaises(Exception, datastore._compute_atom_size, [42])

    def test_empty(self):
        self._assert_sizes([], [])

    def test_rollback(self):
        r1 = self.table.insert(foo=42)
        self._assert_sizes([(r1, self.BASE_FIELD_SIZE)], [self.BASE_FIELD_SIZE])
        self.datastore.rollback()
        self._assert_sizes([], [])

    def test_types(self):
        records = [(self.table.insert(ival=42), self.BASE_FIELD_SIZE),
                   (self.table.insert(lval=42L), self.BASE_FIELD_SIZE),
                   (self.table.insert(fval=42.42), self.BASE_FIELD_SIZE),
                   (self.table.insert(bval=True), self.BASE_FIELD_SIZE),
                   (self.table.insert(dval=datastore.Date()), self.BASE_FIELD_SIZE),
                   (self.table.insert(sval='abc'), self.BASE_FIELD_SIZE + len('abc')),
                   (self.table.insert(uval=u'\u1234'),
                    self.BASE_FIELD_SIZE + len(u'\u1234'.encode('utf-8'))),
                   (self.table.insert(bval=datastore.Bytes(b'\x00\xff')), self.BASE_FIELD_SIZE + 2),
                   (self.table.insert(listval=['a', 'b', 'c']),
                    self.BASE_FIELD_SIZE + self.BASE_ITEM_SIZE*3 + len('abc'))]
        self._assert_sizes(records, (field_size for (_, field_size) in records))

    def test_apply_deltas(self):
        c1 = ChangesBuilder()
        c1.insert('r1', foo=42, baz='abc')
        c1.insert('r2', bar=42)
        c2 = ChangesBuilder()
        c2.delete('r2')
        c3 = ChangesBuilder()
        c3.update('r1', foo='abc', baz=None)
        deltas = [{'rev': 0, 'changes': [ch.to_json() for ch in c1.changes]},
                  {'rev': 1, 'changes': [ch.to_json() for ch in c2.changes]},
                  {'rev': 2, 'changes': [ch.to_json() for ch in c3.changes]},
                  ]
        self.datastore.apply_deltas(deltas)

        # We should be left with only r1 containing a string of length 3.
        self._assert_sizes([(self.table.get('r1'), self.BASE_FIELD_SIZE + 3)], [])

    def test_record_ops(self):
        r1 = self.table.get_or_insert('r1')
        change_sizes = [0]
        self._assert_sizes([(r1, 0)], change_sizes)

        r1.update(foo=42)
        change_sizes.append(self.BASE_FIELD_SIZE)
        self._assert_sizes([(r1, self.BASE_FIELD_SIZE)], change_sizes)

        r1.update(foo=None)
        change_sizes.append(self.BASE_FIELD_SIZE)
        self._assert_sizes([(r1, 0)], change_sizes)

        r1.update(foo='abc', bar='def')
        change_sizes.append((2 * self.BASE_FIELD_SIZE) + len('abcdef'))
        self._assert_sizes([(r1, 2 * self.BASE_FIELD_SIZE + len('abcdef'))], change_sizes)

        r1.delete_record()
        change_sizes.append(0)
        self._assert_sizes([], change_sizes)
        self.assertEquals(r1.get_size(), 0)

    def test_list_ops(self):
        r1 = self.table.get_or_insert('r1')
        change_sizes = [0]
        self._assert_sizes([(r1, 0)], change_sizes)

        l1 = r1.get_or_create_list('l1')
        change_sizes.append(self.BASE_FIELD_SIZE)
        self._assert_sizes([(r1, self.BASE_FIELD_SIZE)], change_sizes)

        l1.append('foo')
        change_sizes.append(self.BASE_FIELD_SIZE + len('foo'))
        l1.append(42)
        change_sizes.append(self.BASE_FIELD_SIZE)
        l1.extend(['bar', datastore.Bytes(b'\x00\xff')])
        change_sizes.append(self.BASE_FIELD_SIZE + len('bar'))
        change_sizes.append(self.BASE_FIELD_SIZE + len(b'\x00\xff'))
        expected_list_size = l1.BASE_ITEM_SIZE * 4 + len('foobar') + len(b'\x00\xff')
        self._assert_sizes([(r1, self.BASE_FIELD_SIZE + expected_list_size)], change_sizes)

        l1.insert(2, 'baz')
        expected_list_size += (l1.BASE_ITEM_SIZE + len('baz'))
        change_sizes.append(self.BASE_FIELD_SIZE + len('baz'))
        self._assert_sizes([(r1, self.BASE_FIELD_SIZE + expected_list_size)], change_sizes)

        # Move shouldn't change the size.
        l1.move(3, 0)
        change_sizes.append(self.BASE_FIELD_SIZE)
        self._assert_sizes([(r1, self.BASE_FIELD_SIZE + expected_list_size)], change_sizes)

        l1.pop()
        expected_list_size -= (l1.BASE_ITEM_SIZE + len(b'\x00\xff'))
        change_sizes.append(self.BASE_FIELD_SIZE)
        self._assert_sizes([(r1, self.BASE_FIELD_SIZE + expected_list_size)], change_sizes)


if __name__ == '__main__':
    unittest.main()
