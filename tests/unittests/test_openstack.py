import mock
import unittest

import simplestreams.openstack as s_openstack


class TestOpenStack(unittest.TestCase):
    MOCK_OS_VARS = {
        'OS_AUTH_TOKEN': 'a-token',
        'OS_AUTH_URL': 'http://0.0.0.0/v2.0',
        'OS_CACERT': 'some-cert',
        'OS_IMAGE_API_VERSION': '2',
        'OS_IMAGE_URL': 'http://1.2.3.4:9292/',
        'OS_PASSWORD': 'some-password',
        'OS_REGION_NAME': 'region1',
        'OS_STORAGE_URL': 'http://1.2.3.4:8080/v1/AUTH_123456',
        'OS_TENANT_ID': '123456789',
        'OS_TENANT_NAME': 'a-project',
        'OS_USERNAME': 'openstack',
        'OS_INSECURE': 'true',
        'OS_USER_DOMAIN_NAME': 'default',
        'OS_PROJECT_DOMAIN_NAME': 'Default',
        'OS_USER_DOMAIN_ID': 'default',
        'OS_PROJECT_DOMAIN_ID': 'default',
        'OS_PROJECT_NAME': 'some-project',
        'OS_PROJECT_ID': 'project-id',
    }

    def test_load_keystone_creds_V2_from_osvars(self):

        with mock.patch('os.environ', new=self.MOCK_OS_VARS.copy()):
            creds = s_openstack.load_keystone_creds()

        self.assertEquals(creds,
                          {'auth_token': 'a-token',
                           'auth_url': 'http://0.0.0.0/v2.0',
                           'cacert': 'some-cert',
                           'image_api_version': '2',
                           'image_url': 'http://1.2.3.4:9292/',
                           'insecure': True,
                           'password': 'some-password',
                           'project_domain_id': 'default',
                           'project_domain_name': 'Default',
                           'project_id': 'project-id',
                           'project_name': 'some-project',
                           'region_name': 'region1',
                           'storage_url': 'http://1.2.3.4:8080/v1/AUTH_123456',
                           'tenant_id': '123456789',
                           'tenant_name': 'a-project',
                           'user_domain_id': 'default',
                           'user_domain_name': 'default',
                           'username': 'openstack'})

    def test_load_keystone_creds_V2_from_kwargs(self):

        with mock.patch('os.environ', new=self.MOCK_OS_VARS.copy()):
            creds = s_openstack.load_keystone_creds(
                password='the-password',
                username='myuser')

        self.assertEquals(creds,
                          {'auth_token': 'a-token',
                           'auth_url': 'http://0.0.0.0/v2.0',
                           'cacert': 'some-cert',
                           'image_api_version': '2',
                           'image_url': 'http://1.2.3.4:9292/',
                           'insecure': True,
                           'password': 'the-password',
                           'project_domain_id': 'default',
                           'project_domain_name': 'Default',
                           'project_id': 'project-id',
                           'project_name': 'some-project',
                           'region_name': 'region1',
                           'storage_url': 'http://1.2.3.4:8080/v1/AUTH_123456',
                           'tenant_id': '123456789',
                           'tenant_name': 'a-project',
                           'user_domain_id': 'default',
                           'user_domain_name': 'default',
                           'username': 'myuser'})

    def test_load_keystone_creds_V3_from_osvars(self):
        v3kwargs = self.MOCK_OS_VARS.copy()
        v3kwargs['OS_AUTH_URL'] = 'http://0.0.0.0/v3'

        with mock.patch('os.environ', new=v3kwargs):
            creds = s_openstack.load_keystone_creds()

        self.assertEquals(creds,
                          {'auth_token': 'a-token',
                           'auth_url': 'http://0.0.0.0/v3',
                           'cacert': 'some-cert',
                           'image_api_version': '2',
                           'image_url': 'http://1.2.3.4:9292/',
                           'insecure': True,
                           'password': 'some-password',
                           'project_domain_id': 'default',
                           'project_domain_name': 'Default',
                           'project_id': 'project-id',
                           'project_name': 'some-project',
                           'region_name': 'region1',
                           'storage_url': 'http://1.2.3.4:8080/v1/AUTH_123456',
                           'tenant_id': '123456789',
                           'tenant_name': 'a-project',
                           'user_domain_id': 'default',
                           'user_domain_name': 'default',
                           'username': 'openstack'})

    def test_load_keystone_creds_insecure(self):
        """test load_keystone_creds behaves correctly for OS_INSECURE values.
        """
        kwargs = self.MOCK_OS_VARS.copy()
        test_pairs = (('off', False),
                      ('no', False),
                      ('false', False),
                      ('', False),
                      ('anything-else', True))
        for val, expected in test_pairs:
            kwargs['OS_INSECURE'] = val
            with mock.patch('os.environ', new=kwargs):
                creds = s_openstack.load_keystone_creds()
            self.assertEqual(creds['insecure'], expected)

    def test_load_keystone_creds_verify(self):
        """Test that cacert comes across as verify."""
        kwargs = self.MOCK_OS_VARS.copy()

        with mock.patch('os.environ', new=kwargs):
            creds = s_openstack.load_keystone_creds()
        self.assertNotIn('verify', creds)

        kwargs['OS_INSECURE'] = 'false'
        with mock.patch('os.environ', new=kwargs):
            creds = s_openstack.load_keystone_creds()
        self.assertEqual(creds['verify'], kwargs['OS_CACERT'])

        kwargs['OS_INSECURE'] = 'false'
        del kwargs['OS_CACERT']
        with mock.patch('os.environ', new=kwargs):
            creds = s_openstack.load_keystone_creds()
        self.assertNotIn('verify', creds)

    def test_load_keystone_creds_missing(self):
        kwargs = self.MOCK_OS_VARS.copy()
        del kwargs['OS_USERNAME']
        with mock.patch('os.environ', new=kwargs):
            with self.assertRaises(ValueError):
                s_openstack.load_keystone_creds()

        kwargs = self.MOCK_OS_VARS.copy()
        del kwargs['OS_AUTH_URL']
        with mock.patch('os.environ', new=kwargs):
            with self.assertRaises(ValueError):
                s_openstack.load_keystone_creds()

        # either auth_token or password needs to be exist, but if both are
        # missing then raise an exception
        kwargs = self.MOCK_OS_VARS.copy()
        del kwargs['OS_AUTH_TOKEN']
        with mock.patch('os.environ', new=kwargs):
            s_openstack.load_keystone_creds()
        kwargs = self.MOCK_OS_VARS.copy()
        del kwargs['OS_PASSWORD']
        with mock.patch('os.environ', new=kwargs):
            s_openstack.load_keystone_creds()
        kwargs = self.MOCK_OS_VARS.copy()
        del kwargs['OS_AUTH_TOKEN']
        del kwargs['OS_PASSWORD']
        with mock.patch('os.environ', new=kwargs):
            with self.assertRaises(ValueError):
                s_openstack.load_keystone_creds()

        # API version 3
        for k in ('OS_USER_DOMAIN_NAME',
                  'OS_PROJECT_DOMAIN_NAME',
                  'OS_PROJECT_NAME'):
            kwargs = self.MOCK_OS_VARS.copy()
            kwargs['OS_AUTH_URL'] = 'http://0.0.0.0/v3'
            del kwargs[k]
            with self.assertRaises(ValueError):
                s_openstack.load_keystone_creds()

    @mock.patch.object(s_openstack, '_LEGACY_CLIENTS', new=False)
    @mock.patch.object(s_openstack.session, 'Session')
    def test_get_ksclient_v2(self, m_session):
        kwargs = self.MOCK_OS_VARS.copy()
        mock_ksclient_v2 = mock.Mock()
        mock_ident_v2 = mock.Mock()
        with mock.patch.object(
                s_openstack, 'KS_VERSION_RESOLVER', new={}) as m:
            m[2] = s_openstack.Settings(mod=mock_ksclient_v2,
                                        ident=mock_ident_v2,
                                        arg_set=s_openstack.PASSWORD_V2)

            # test openstack ks 2
            m_auth = mock.Mock()
            mock_ident_v2.Password.return_value = m_auth
            m_get_access = mock.Mock()
            m_auth.get_access.return_value = m_get_access
            m_session.return_value = mock.sentinel.session

            with mock.patch('os.environ', new=kwargs):
                creds = s_openstack.load_keystone_creds()

            c = s_openstack.get_ksclient(**creds)
            # verify that mock_ident_v2 is called with password
            mock_ident_v2.Password.assert_has_calls([
                mock.call(auth_url='http://0.0.0.0/v2.0',
                          password='some-password',
                          tenant_id='123456789',
                          tenant_name='a-project',
                          username='openstack')])
            # verify that the session was called with the v2 password
            m_session.assert_called_once_with(auth=m_auth)
            # verify that the client was called with the session
            mock_ksclient_v2.Client.assert_called_once_with(
                session=mock.sentinel.session)
            # finally check that the client as an auth_ref and that it contains
            # the get_access() call
            self.assertEqual(c.auth_ref, m_get_access)
            m_auth.get_access.assert_called_once_with(mock.sentinel.session)

    @mock.patch.object(s_openstack, '_LEGACY_CLIENTS', new=False)
    @mock.patch.object(s_openstack.session, 'Session')
    def test_get_ksclient_v3(self, m_session):
        kwargs = self.MOCK_OS_VARS.copy()
        kwargs['OS_AUTH_URL'] = 'http://0.0.0.0/v3'
        mock_ksclient_v3 = mock.Mock()
        mock_ident_v3 = mock.Mock()
        with mock.patch.object(
                s_openstack, 'KS_VERSION_RESOLVER', new={}) as m:
            m[3] = s_openstack.Settings(mod=mock_ksclient_v3,
                                        ident=mock_ident_v3,
                                        arg_set=s_openstack.PASSWORD_V3)

            # test openstack ks 3
            m_auth = mock.Mock()
            mock_ident_v3.Password.return_value = m_auth
            m_get_access = mock.Mock()
            m_auth.get_access.return_value = m_get_access
            m_session.return_value = mock.sentinel.session

            with mock.patch('os.environ', new=kwargs):
                creds = s_openstack.load_keystone_creds()

            c = s_openstack.get_ksclient(**creds)
            # verify that mock_ident_v2 is called with password
            mock_ident_v3.Password.assert_has_calls([
                mock.call(auth_url='http://0.0.0.0/v3',
                          password='some-password',
                          project_domain_id='default',
                          project_domain_name='Default',
                          project_id='project-id',
                          project_name='some-project',
                          user_domain_id='default',
                          user_domain_name='default',
                          username='openstack')])
            # verify that the session was called with the v2 password
            m_session.assert_called_once_with(auth=m_auth)
            # verify that the client was called with the session
            mock_ksclient_v3.Client.assert_called_once_with(
                session=mock.sentinel.session)
            # finally check that the client as an auth_ref and that it contains
            # the get_access() call
            self.assertEqual(c.auth_ref, m_get_access)
            m_auth.get_access.assert_called_once_with(mock.sentinel.session)
