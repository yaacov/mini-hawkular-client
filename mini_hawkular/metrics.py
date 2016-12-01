"""
   Copyright 2015-2016 Red Hat, Inc. and/or its affiliates
   and other contributors.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""
from __future__ import unicode_literals

import codecs
import time
import collections
import base64
import ssl

try:
    import simplejson as json
except ImportError:
    import json

# Fall back to Python 2's urllib2
from urllib2 import Request, urlopen, URLError, HTTPError, HTTPErrorProcessor, build_opener, install_opener
from urllib import quote, urlencode

class MetricType:
    Gauge = 'gauges'
    Availability = 'availability'
    Counter = 'counters'
    String = 'strings'
    Rate = 'rate'
    _Metrics = 'metrics'

    @staticmethod
    def short(metric_type):
        if metric_type is MetricType.Gauge:
            return 'gauge'
        elif metric_type is MetricType.Counter:
            return 'counter'
        elif metric_type is MetricType.String:
            return 'string'
        else:
            return 'availability'

class HawkularMetricsError(HTTPError):
    pass
        
class HawkularMetricsConnectionError(URLError):
    pass

class HawkularHTTPErrorProcessor(HTTPErrorProcessor):
    """
    Hawkular-Metrics uses http codes 201, 204
    """
    def http_response(self, request, response):

        if response.code in [200, 201, 204]:
            return response
        return HTTPErrorProcessor.http_response(self, request, response)
  
    https_response = http_response

class HawkularMetricsClient:
    """
    Creates new client for Hawkular-Metrics. As tenant_id, give intended tenant_id, even if it's not
    created yet. To change the instance's tenant_id, use tenant(tenant_id) method
    """
    def __init__(self,
                 tenant_id,
                 host='localhost',
                 port=8080,
                 path='hawkular/metrics',
                 scheme='http',
                 cafile=None,
                 context=None,
                 token=None,
                 username=None,
                 password=None):
        """
        A new instance of HawkularMetricsClient is created with the following defaults:

        host = localhost
        port = 8081
        path = hawkular-metrics
        scheme = http
        cafile = None

        The url that is called by the client is:

        {scheme}://{host}:{port}/{2}/
        """
        self.tenant_id = tenant_id
        self.host = host
        self.port = port
        self.path = path
        self.cafile = cafile
        self.scheme = scheme
        self.context = context
        self.token = token
        self.username = username
        self.password = password

        opener = build_opener(HawkularHTTPErrorProcessor())
        install_opener(opener)

    """
    Internal methods
    """
    @staticmethod
    def _clean_metric_id(metric_id):
        return quote(metric_id, '')

    def _get_base_url(self):
        return "{0}://{1}:{2}/{3}/".format(self.scheme, self.host, str(self.port), self.path)
    
    def _get_url(self, metric_type=None):
        if metric_type is None:
            metric_type = MetricType._Metrics

        return self._get_base_url() + '{0}'.format(metric_type)

    def _get_metrics_single_url(self, metric_type, metric_id):
        return self._get_url(metric_type) + '/{0}'.format(self._clean_metric_id(metric_id))

    def _get_metrics_raw_url(self, metrics_url):
        return metrics_url + '/raw'

    def _get_metrics_tags_url(self, metrics_url):
        return metrics_url + '/tags'
    
    def _http(self, url, method, data=None):
        res = None

        try:
            req = Request(url=url)
            req.add_header('Content-Type', 'application/json')
            req.add_header('Hawkular-Tenant', self.tenant_id)
            req.add_header('Host', self.host)

            if self.token is not None:
                req.add_header('Authorization', 'Bearer {0}'.format(self.token))
            elif self.username is not None:
                req.add_header('Authorization', 'Basic {0}'.format(base64.b64encode(self.username + b':' + self.password)))

            if not isinstance(data, str):
                data = json.dumps(data, indent=2)

            # writer = codecs.getencoder('utf-8')
            reader = codecs.getreader('utf-8')

            if data:
                try:
                    req.add_data(data)
                except AttributeError:
                    req.data = data.encode('utf-8')

            req.get_method = lambda: method
            res = urlopen(req, context = self.context)

        except Exception as e:
            self._handle_error(e)

        finally:
            if res:
                res.close()        
    
    def _put(self, url, data):
        self._http(url, 'PUT', data)

    def _post(self, url, data):
        self._http(url, 'POST', data)
       
    def _handle_error(self, e):
        if isinstance(e, HTTPError):
            # Cast to HawkularMetricsError
            e.__class__ = HawkularMetricsError
            err_json = e.read()

            try:
                err_d = json.loads(err_json)
                e.msg = err_d['errorMsg']
            except:
                # Keep the original payload, couldn't parse it
                e.msg = err_json

            raise e
        elif isinstance(e, URLError):
            # Cast to HawkularMetricsConnectionError
            e.__class__ = HawkularMetricsConnectionError
            e.msg = "Error, could not send event(s) to the Hawkular Metrics: " + str(e.reason)
            raise e
        else:
            raise e
        
    def _isfloat(value):
        try:
            float(value)
            return True
        except ValueError:
            return False
        
    """
    External methods
    """    

    def tenant(self, tenant_id):
        self.tenant_id = tenant_id

    """
    Instance methods
    """
    
    def put(self, data):
        """
        Send multiple different metric_ids to the server in a single batch. Metrics can be a mixture
        of types.

        data is a dict or a list of dicts created with create_metric(metric_type, metric_id, datapoints)
        """
        if not isinstance(data, list):
            data = [data]

        r = collections.defaultdict(list)

        for d in data:
            metric_type = d.pop('type', None)
            if metric_type is None:
                raise HawkularMetricsError('Undefined MetricType')
            r[metric_type].append(d)

        # This isn't transactional, but .. ouh well. One can always repost everything.
        for l in r:
            self._post(self._get_metrics_raw_url(self._get_url(l)), r[l])

    def push(self, metric_type, metric_id, value, timestamp=None):
        """
        Pushes a single metric_id, datapoint combination to the server.

        This method is an assistant method for the put method by removing the need to
        create data structures first.
        """
        item = create_metric(metric_type, metric_id, create_datapoint(value, timestamp))
        self.put(item)

    def update_metric_tags(self, metric_type, metric_id, **tags):
        """
        Replace the metric_id's tags with given **tags
        """
        self._put(self._get_metrics_tags_url(self._get_metrics_single_url(metric_type, metric_id)), tags)

"""
Static methods
"""
def time_millis():
    """
    Returns current milliseconds since epoch
    """
    return int(round(time.time() * 1000))

def create_datapoint(value, timestamp=None, **tags):
    """
    Creates a single datapoint dict with a value, timestamp (optional - filled by the method if missing)
    and tags (optional)
    """
    if timestamp is None:
        timestamp = time_millis()

    item = { 'timestamp': timestamp,
             'value': value }

    if tags is not None:
        item['tags'] = tags

    return item

def create_metric(metric_type, metric_id, data):
    """
    Create Hawkular-Metrics' submittable structure, data is a datapoint or list of datapoints
    """
    if not isinstance(data, list):
        data = [data]
    
    return { 'type': metric_type,'id': metric_id, 'data': data }
        
