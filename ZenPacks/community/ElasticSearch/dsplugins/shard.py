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


class Shard(PythonDataSourcePlugin):
    proxy_attributes = (
        'zElasticSearchUseSSL',
        'zElasticSearchPort',
    )

    state_maps = {
        'STARTED': 0,
        'UNASSIGNED': 1,
    }

    state_severity_maps = {
        'STARTED': 0,
        'UNASSIGNED': 5,
    }

    @classmethod
    def config_key(cls, datasource, context):
        log.info('In config_key {} {} {}'.format(context.device().id,
                                                 datasource.getCycleTime(context),
                                                 'ShardStats'))

        return (context.device().id,
                datasource.getCycleTime(context),
                'ShardStats'
        )

    @classmethod
    def params(cls, datasource, context):
        params = {}
        params['index_id'] = context.index_id
        params['shard_id'] = context.shard_id
        return params

    @inlineCallbacks
    def collect(self, config):
        log.debug('Starting ShardStats collect')

        ds0 = config.datasources[0]
        scheme = 'https' if ds0.zElasticSearchUseSSL else 'http'
        url = '{}://{}:{}/_cluster/state/routing_table'.format(scheme, config.id, ds0.zElasticSearchPort)

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
        log.debug('Success shard job - result is {}'.format(result))
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
        for ds in config.datasources:
            comp_id = ds.component
            index_id = ds.params['index_id']
            shard_id = ds.params['shard_id']
            shard_data = result['routing_table']['indices'][index_id]['shards'][shard_id][0]
            '''
            {u'node': u'iiZfj8H3Tj2bP0-MTPecsg', u'index': u'graylog_2', 
                u'allocation_id': {u'id': u'AEOTB5uXRW2xVETtEA6clw'}, u'primary': True, u'shard': 0, 
                u'state': u'STARTED', u'relocating_node': None}
             {u'node': None, u'index': u'graylog_2', u'primary': True, u'shard': 3, 
                u'recovery_source': {u'bootstrap_new_history_uuid': False, u'type': u'EXISTING_STORE'}, 
                u'state': u'UNASSIGNED', u'relocating_node': None, 
                u'unassigned_info': {u'failed_attempts': 1, u'delayed': False, u'reason': u'ALLOCATION_FAILED', 
                    u'details': u'failed shard on node [iiZfj8H3Tj2bP0-MTPecsg]: shard failure, reason [refresh failed source[schedule]], failure CorruptIndexException[misplaced codec footer (file truncated?): remaining=8, expected=16, fp=33 (resource=BufferedChecksumIndexInput(NIOFSIndexInput(path="/usr/share/elasticsearch/data/nodes/0/indices/_jSUEbQ_RWSasx5bGxdZ_Q/3/index/_i1c_Lucene85FieldsIndex-doc_ids_5tw.tmp")))]', 
                    u'allocation_status': u'no_valid_shard_copy', u'at': u'2021-05-18T07:36:35.707Z'}}
            '''
            state = shard_data['state'].upper()
            state_value = self.state_maps.get(state, 2)
            data['values'][comp_id]['shard_state'] = state_value
            summary = 'Shard {} - State is {}'.format(comp_id, state.upper())
            if 'unassigned_info' in shard_data:
                message = shard_data['unassigned_info']['details']
            else:
                message = summary
            data['events'].append({
                'device': config.id,
                'component': comp_id,
                'severity': self.state_severity_maps.get(state, 0),
                'eventKey': 'ClusterStatus',
                'eventClassKey': 'ClusterStatus',
                'summary': summary,
                'message': message,
                'eventClass': '/Status/ElasticSearch/Shard',
            })


        return data

    def onError(self, result, config):
        log.error('Error - result is {}'.format(result))
        # TODO: send event of collection failure
        return {}
