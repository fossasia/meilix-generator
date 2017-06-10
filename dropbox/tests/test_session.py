import mock
import unittest
import urllib

from dropbox.session import DropboxSession

def _create_generic_session(rest_client, consumer_key='a',
                            consumer_secret='b', access_type='app_folder'):
    return DropboxSession(consumer_key, consumer_secret, access_type, rest_client=rest_client)

class TestClientUsage(unittest.TestCase):
    def test_set_token(self):
        access_token = ('c', 'd')

        mock_rest_client = mock.Mock()

        a = _create_generic_session(mock_rest_client)
        a.set_token(*access_token)

        self.assertEqual(a.token.key, access_token[0])
        self.assertEqual(a.token.secret, access_token[1])

    def test_set_request_token(self):
        request_token = ('c', 'd')
        mock_rest_client = mock.Mock()

        a = _create_generic_session(mock_rest_client)
        a.set_request_token(*request_token)

        self.assertEqual(a.request_token.key, request_token[0])
        self.assertEqual(a.request_token.secret, request_token[1])

    def test_API_CONTENT_HOST(self):
        a = _create_generic_session(None)
        self.assertEqual(a.API_CONTENT_HOST, 'api-content.dropbox.com')

    def test_API_HOST(self):
        a = _create_generic_session(None)
        self.assertEqual(a.API_HOST, 'api.dropbox.com')

    def test_build_url_simple(self):
        a = _create_generic_session(None)
        base = a.build_url('api.dropbox.com', '/dropbox/metadata')
        self.assertEqual(base, 'https://api.dropbox.com/1/dropbox/metadata')

    def test_build_url_params(self):
        a = _create_generic_session(None)
        params = {'foo' : 'bar', 'baz' : '1 2'}
        base = a.build_url('api.dropbox.com', '/dropbox/metadata', params)
        self.assertEqual(base, 'https://api.dropbox.com/1/dropbox/metadata?' + urllib.urlencode(params))

    def test_root_app_folder(self):
        a = _create_generic_session(None)
        self.assertEqual(a.root, 'sandbox')

    def test_root_dropbox(self):
        a = _create_generic_session(None, access_type='dropbox')
        self.assertEqual(a.root, 'dropbox')

class TestSession(unittest.TestCase):
    def test_obtain_access_token_no_request_token(self):
        mock_rest_client = mock.Mock()
        sess = _create_generic_session(mock_rest_client)
        self.assertRaises(Exception, sess.obtain_access_token)

    def test_obtain_request_token(self):
        # setup mocks
        request_token = ('a', 'b')
        new_request_token_res = dict(oauth_token=request_token[0],
                                     oauth_token_secret=request_token[1])

        mock_rest_client = mock.Mock()
        mock_response = mock.Mock()

        mock_rest_client.POST.return_value = mock_response
        mock_response.read.return_value = urllib.urlencode(new_request_token_res)

        # make call
        sess = _create_generic_session(mock_rest_client)
        rt = sess.obtain_request_token()

        # assert correctness
        url = 'https://api.dropbox.com/1/oauth/request_token'
        mock_rest_client.POST.assert_called_with(url, headers={}, params=mock.ANY,
                                                 raw_response=True)
        # TODO: maybe we can be less strict about the exact oauth headers
        _, kwargs = mock_rest_client.POST.call_args
        params = kwargs['params']
        self.assertEqual(params['oauth_consumer_key'], sess.consumer_creds.key)
        self.assertEqual(params['oauth_version'], '1.0')
        self.assertEqual(params['oauth_signature_method'], 'PLAINTEXT')
        self.assertEqual(params['oauth_signature'], '%s&' % sess.consumer_creds.secret)

        self.assertEqual(rt.key, request_token[0])
        self.assertEqual(rt.secret, request_token[1])

        self.assertEqual(sess.request_token.key, request_token[0])
        self.assertEqual(sess.request_token.secret, request_token[1])

    def _obtain_access_token(self, call):
        class request_token:
            key = 'a'
            secret = 'b'

        access_token = ('a', 'b')
        new_access_token_res = dict(oauth_token=access_token[0],
                                    oauth_token_secret=access_token[1])

        mock_rest_client = mock.Mock()
        mock_response = mock.Mock()

        mock_rest_client.POST.return_value = mock_response
        mock_response.read.return_value = urllib.urlencode(new_access_token_res)

        # make call
        sess = _create_generic_session(mock_rest_client)
        at = call(sess, request_token)

        # assert correctness
        url = 'https://api.dropbox.com/1/oauth/access_token'
        mock_rest_client.POST.assert_called_with(url, headers={}, params=mock.ANY,
                                                 raw_response=True)
        # TODO: maybe we can be less strict about the exact oauth headers
        _, kwargs = mock_rest_client.POST.call_args
        params = kwargs['params']
        self.assertEqual(params['oauth_consumer_key'], sess.consumer_creds.key)
        self.assertEqual(params['oauth_version'], '1.0')
        self.assertEqual(params['oauth_signature_method'], 'PLAINTEXT')
        self.assertEqual(params['oauth_signature'],
                         '%s&%s' % (sess.consumer_creds.secret, request_token.secret))
        self.assertEqual(params['oauth_token'], request_token.key)
        self.assertEqual(frozenset(params),
                         frozenset(['oauth_consumer_key',
                                    'oauth_timestamp',
                                    'oauth_nonce',
                                    'oauth_version',
                                    'oauth_signature_method',
                                    'oauth_signature',
                                    'oauth_token']))

        self.assertEqual(at.key, access_token[0])
        self.assertEqual(at.secret, access_token[1])

        self.assertEqual(sess.token.key, access_token[0])
        self.assertEqual(sess.token.secret, access_token[1])

    def test_obtain_access_token_passed_in_request_token(self):
        def call(sess, request_token):
            return sess.obtain_access_token(request_token=request_token)
        self._obtain_access_token(call)

    def test_obtain_access_token_set_request_token(self):
        def call(sess, request_token):
            sess.set_request_token(request_token.key, request_token.secret)
            return sess.obtain_access_token()
        self._obtain_access_token(call)

    def test_build_authorize_url(self):
        mock_rest_client = mock.Mock()

        sess = _create_generic_session(mock_rest_client)

        class request_token:
            key = 'a'
            secret = 'b'
        callback = 'http://www.dropbox.com/callback'

        ret = sess.build_authorize_url(request_token, callback)

        # TODO: a better test would be to parse out the encoded params
        # and compare, or compare url objects
        self.assertEqual('https://www.dropbox.com/1/oauth/authorize?' +
                         urllib.urlencode({'oauth_token' : request_token.key,
                                           'oauth_callback' : callback}),
                         ret)

    def test_is_linked(self):
        sess = _create_generic_session(None)
        self.assertFalse(sess.is_linked())
        sess.set_token('a', 'b')
        self.assertTrue(sess.is_linked())

    def _parse_token_fail(self, return_value):
        mock_rest_client = mock.Mock()
        mock_response = mock.Mock()

        mock_rest_client.POST.return_value = mock_response
        mock_response.read.return_value = return_value

        sess = _create_generic_session(mock_rest_client)

        self.assertRaises(Exception, sess.obtain_request_token)

    def test_parse_token_fail_empty(self):
        self._parse_token_fail('')

    def test_parse_token_fail_empty(self):
        self._parse_token_fail(urllib.urlencode({}))

    def test_parse_token_fail_no_oauth_token(self):
        self._parse_token_fail(urllib.urlencode({'something': '1'}))

    def test_parse_token_fail_no_oauth_token_secret(self):
        self._parse_token_fail(urllib.urlencode({'oauth_token': '1'}))




