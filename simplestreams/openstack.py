#   Copyright (C) 2013 Canonical Ltd.
#
#   Author: Scott Moser <scott.moser@canonical.com>
#
#   Simplestreams is free software: you can redistribute it and/or modify it
#   under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   Simplestreams is distributed in the hope that it will be useful, but
#   WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
#   or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Affero General Public
#   License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with Simplestreams.  If not, see <http://www.gnu.org/licenses/>.

import collections
import os

from keystoneclient.v2_0 import client as ksclient_v2
from keystoneclient.v3 import client as ksclient_v3
try:
    from keystoneauth1 import session
    from keystoneauth1.identity import (v2, v3)
    _LEGACY_CLIENTS = False
except ImportError:
    # 14.04 level packages do not have this.
    session, v2, v3 = (None, None, None)
    _LEGACY_CLIENTS = True


OS_ENV_VARS = (
    'OS_AUTH_TOKEN', 'OS_AUTH_URL', 'OS_CACERT', 'OS_IMAGE_API_VERSION',
    'OS_IMAGE_URL', 'OS_PASSWORD', 'OS_REGION_NAME', 'OS_STORAGE_URL',
    'OS_TENANT_ID', 'OS_TENANT_NAME', 'OS_USERNAME', 'OS_INSECURE',
    'OS_USER_DOMAIN_NAME', 'OS_PROJECT_DOMAIN_NAME',
    'OS_USER_DOMAIN_ID', 'OS_PROJECT_DOMAIN_ID', 'OS_PROJECT_NAME',
    'OS_PROJECT_ID'
)


PT_V2 = ('username', 'password', 'tenant_id', 'tenant_name', 'auth_url',
         'cacert', 'insecure', )
PT_V3 = ('username', 'password', 'project_id', 'project_name', 'auth_url',
         'cacert', 'insecure', 'user_domain_name', 'project_domain_name',
         'user_domain_id', 'project_domain_id', )


Settings = collections.namedtuple('Settings', 'mod ident arg_set')
KS_VERSION_RESOLVER = {2: Settings(mod=ksclient_v2,
                                   ident=v2,
                                   arg_set=PT_V2),
                       3: Settings(mod=ksclient_v3,
                                   ident=v3,
                                   arg_set=PT_V3), }


def load_keystone_creds(**kwargs):
    # either via arguments or OS_* values in environment, the kwargs
    # that are required are:
    #   'username', 'auth_url',
    #   ('auth_token' or 'password')
    #   ('tenant_id' or 'tenant_name')
    ret = {}
    for name in OS_ENV_VARS:
        lc = name.lower()
        # take off 'os_'
        short = lc[3:]
        if short in kwargs:
            ret[lc] = kwargs.get(lc)
        elif name in os.environ:
            # take off 'os_'
            ret[short] = os.environ[name]

    if 'insecure' in ret:
        if isinstance(ret['insecure'], str):
            ret['insecure'] = (ret['insecure'].lower() not in
                               ("", "0", "no", "off"))
        else:
            ret['insecure'] = bool(ret['insecure'])

    missing = []
    for req in ('username', 'auth_url'):
        if not ret.get(req):
            missing.append(req)

    if not (ret.get('auth_token') or ret.get('password')):
        missing.append("(auth_token or password)")

    api_version = get_ks_api_version(ret.get('auth_url', '')) or 2
    if (api_version == 2 and
            not (ret.get('tenant_id') or ret.get('tenant_name'))):
        raise ValueError("(tenant_id or tenant_name)")

    if (api_version == 3 and
            not (ret.get('user_domain_name') and
                 ret.get('project_domain_name') and
                 ret.get('project_name'))):
        raise ValueError("(user_domain_name, project_domain_name "
                         "or project_name)")

    if missing:
        raise ValueError("Need values for: %s" % missing)

    return ret


def get_regions(client=None, services=None, kscreds=None):
    # if kscreds had 'region_name', then return that
    if kscreds and kscreds.get('region_name'):
        return [kscreds.get('region_name')]

    if client is None:
        creds = kscreds
        if creds is None:
            creds = load_keystone_creds()
        client = get_ksclient(**creds)

    endpoints = client.service_catalog.get_endpoints()
    if services is None:
        services = list(endpoints.keys())
    regions = set()
    for service in services:
        for r in endpoints.get(service, {}):
            regions.add(r['region'])

    return list(regions)


def get_ks_api_version(auth_url=None, env=None):
    """Get the keystone api version based on the end of the auth url.

    @param auth_url: String
    @returns: 2 or 3 (int)
    """
    if env is None:
        env = os.environ

    if env.get('OS_IDENTITY_API_VERSION'):
        return int(env['OS_IDENTITY_API_VERSION'])

    if auth_url is None:
        auth_url = ""

    if auth_url.endswith('/v3'):
        return 3
    elif auth_url.endswith('/v2.0'):
        return 2
    # Return None if we can't determine the keystone version
    return None


def _legacy_ksclient(**kwargs):
    """14.04 does not have session available."""
    kskw = {k: kwargs.get(k) for k in PT_V2 if k in kwargs}
    return ksclient_v2.Client(**kskw)


def get_ksclient(**kwargs):
    # api version will be force to 3 or 2
    if _LEGACY_CLIENTS:
        return _legacy_ksclient(**kwargs)

    api_version = get_ks_api_version(kwargs.get('auth_url', '')) or 2
    arg_set = KS_VERSION_RESOLVER[api_version].arg_set
    # Filter/select the args for the api version from the kwargs dictionary
    kskw = {k: v for k, v in kwargs.items() if k in arg_set}
    auth = KS_VERSION_RESOLVER[api_version].ident.Password(**kskw)
    sess = session.Session(auth=auth)
    client = KS_VERSION_RESOLVER[api_version].mod.Client(session=sess)
    client.auth_ref = auth.get_access(sess)
    return client


def get_service_conn_info(service='image', client=None, **kwargs):
    # return a dict with token, insecure, cacert, endpoint
    if not client:
        client = get_ksclient(**kwargs)

    endpoint = _get_endpoint(client, service, **kwargs)
    # Session client does not have tenant_id set at client.tenant_id
    # If client.tenant_id not set use method to get it
    tenant_id = (client.tenant_id or client.get_project_id(client.session) or
                 client.auth.client.get_project_id())
    info = {'token': client.auth_token, 'insecure': kwargs.get('insecure'),
            'cacert': kwargs.get('cacert'), 'endpoint': endpoint,
            'tenant_id': tenant_id}
    if not _LEGACY_CLIENTS:
        info['session'] = client.session

    return info


def _get_endpoint(client, service, **kwargs):
    """Get an endpoint using the provided keystone client."""
    endpoint_kwargs = {
        'service_type': service,
        'interface': kwargs.get('endpoint_type') or 'publicURL',
        'region_name': kwargs.get('region_name'),
    }
    if _LEGACY_CLIENTS:
        del endpoint_kwargs['interface']

    endpoint = client.service_catalog.url_for(**endpoint_kwargs)
    return endpoint
