from keystoneclient.v2_0 import client as ksclient
import os
import re

import glanceclient

OS_ENV_VARS = (
    'OS_AUTH_TOKEN', 'OS_AUTH_URL', 'OS_CACERT', 'OS_IMAGE_API_VERSION',
    'OS_IMAGE_URL', 'OS_PASSWORD', 'OS_REGION_NAME', 'OS_STORAGE_URL',
    'OS_TENANT_ID', 'OS_TENANT_NAME', 'OS_USERNAME', 'OS_INSECURE'
)


def load_keystone_creds(**kwargs):
    ret = {}
    for name in OS_ENV_VARS:
        lc = name.lower()
        if lc in kwargs:
            ret[lc] = kwargs.get(lc)
        elif name in os.environ:
            # take off 'os_'
            ret[lc[3:]] = os.environ[name]

    if 'insecure' in ret:
        if isinstance(insecure, str):
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
        
    if not (ret.get('tenant_id') or ret.get('tenant_name')):
        raise ValueErorr("(tenant_id or tenant_name)")

    if missing:
        raise ValueError("Need values for: %s" % missing)

    return ret


def get_ksclient(**kwargs):
    pt = ('username', 'password', 'tenant_id', 'tenant_name', 'auth_url',
          'cacert', 'insecure')
    kskw = {k: kwargs.get(k) for k in pt if k in kwargs}
    return ksclient.Client(**kskw)


def get_service_conn_info(service='image', client=None, **kwargs):
    # return a dict with token, insecure, cacert, endpoint
    if not client:
        client = get_ksclient(**kwargs)

    endpoint = _get_endpoint(client, service, **kwargs)
    return {'token': client.auth_token, 'insecure': kwargs.get('insecure'),
            'cacert': kwargs.get('cacert'), 'endpoint': endpoint,
            'tenant_id': client.tenant_id}


def _get_endpoint(client, service, **kwargs):
    """Get an endpoint using the provided keystone client."""
    endpoint_kwargs = {
        'service_type': service,
        'endpoint_type': kwargs.get('endpoint_type') or 'publicURL',
    }

    if kwargs.get('region_name'):
        endpoint_kwargs['attr'] = 'region'
        endpoint_kwargs['filter_value'] = kwargs.get('region_name')

    endpoint = client.service_catalog.url_for(**endpoint_kwargs)
    return _strip_version(endpoint)


def _strip_version(endpoint):
    """Strip a version from the last component of an endpoint if present"""

    # Get rid of trailing '/' if present
    if endpoint.endswith('/'):
        endpoint = endpoint[:-1]
    url_bits = endpoint.split('/')
    # regex to match 'v1' or 'v2.0' etc
    if re.match('v\d+\.?\d*', url_bits[-1]):
        endpoint = '/'.join(url_bits[:-1])
    return endpoint
