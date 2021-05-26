import base64
import json
import logging

from ZenPacks.community.ElasticSearch.lib.utils import SkipCertifContextFactory
# Zenoss imports
from ZenPacks.zenoss.PythonCollector.datasources.PythonDataSource import PythonDataSourcePlugin
# Twisted Imports
from twisted.internet import reactor
from twisted.internet.defer import returnValue, inlineCallbacks
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers

# Setup logging
log = logging.getLogger('zen.ClusterHealth')


class Health(PythonDataSourcePlugin):
    proxy_attributes = (
        'zElasticSearchUseSSL',
        'zElasticSearchPort',
    )

    status_maps = {
        'green': 0,
        'yellow': 1,
        'red': 2,
    }

    status_severity_maps = {
        'green': 0,
        'yellow': 3,
        'red': 5,
    }

    @classmethod
    def config_key(cls, datasource, context):
        log.info('In config_key {} {} {}'.format(context.device().id,
                                                 datasource.getCycleTime(context),
                                                 'ClusterHealth'))

        return (context.device().id,
                datasource.getCycleTime(context),
                'ClusterHealth'
        )

    @classmethod
    def params(cls, datasource, context):
        return {
        }

    @inlineCallbacks
    def collect(self, config):
        log.debug('Starting ClusterHealth collect')

        ds0 = config.datasources[0]
        scheme = 'https' if ds0.zElasticSearchUseSSL else 'http'
        url = '{}://{}:{}/_cluster/health'.format(scheme, config.id, ds0.zElasticSearchPort)

        agent = Agent(reactor, contextFactory=SkipCertifContextFactory())
        headers = {
            "Accept": ['application/json'],
        }
        try:
            response = yield agent.request('GET', url, Headers(headers))
            response_body = yield readBody(response)
            response_body = json.loads(response_body)
            returnValue(response_body)
        except Exception as e:
            log.exception('{}: failed to get server data for {}'.format(config.id, ds0))
            log.exception('{}: Exception: {}'.format(config.id, e))
        returnValue()

    def onSuccess(self, result, config):
        log.debug('Success job - result is {}'.format(result))
        '''
        {u'status': u'red', u'number_of_nodes': 3, u'unassigned_shards': 1, u'number_of_pending_tasks': 0, 
            u'number_of_in_flight_fetch': 0, u'timed_out': False, u'active_primary_shards': 5, 
            u'task_max_waiting_in_queue_millis': 0, u'cluster_name': u'graylog', u'relocating_shards': 0, 
            u'active_shards_percent_as_number': 83.33333333333334, u'active_shards': 5, u'initializing_shards': 0, 
            u'number_of_data_nodes': 3, u'delayed_unassigned_shards': 0}
        '''

        # Status
        data = self.new_data()
        datasource = config.datasources[0]
        comp_id = datasource.component
        status = result['status'].lower()
        status_value = self.status_maps.get(status, 0)
        data['values'][comp_id]['health_status'] = status_value
        data['events'].append({
            'device': config.id,
            'component': comp_id,
            'severity': self.status_severity_maps.get(status, 0),
            'eventKey': 'ClusterStatus',
            'eventClassKey': 'ClusterStatus',
            'summary': 'Cluster {} - Status is {}'.format(comp_id, status.upper()),
            'message': 'Cluster {} - Status is {}'.format(comp_id, status.upper()),
            'eventClass': '/Status/ElasticSearch/Cluster',
        })

        # Other metrics
        for dp in datasource.points:
            if dp.id == 'status':
                continue
            if dp.id in result:
                value = result[dp.id]
                data['values'][comp_id][dp.dpName] = value
        return data

    def onError(self, result, config):
        log.error('Error - result is {}'.format(result))
        # TODO: send event of collection failure
        return {}
