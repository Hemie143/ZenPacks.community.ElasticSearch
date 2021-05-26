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


class Node(PythonDataSourcePlugin):
    proxy_attributes = (
        'zElasticSearchUseSSL',
        'zElasticSearchPort',
    )

    @classmethod
    def config_key(cls, datasource, context):
        log.info('In config_key {} {} {}'.format(context.device().id,
                                                 datasource.getCycleTime(context),
                                                 'ESNode'))

        return (context.device().id,
                datasource.getCycleTime(context),
                'ESNode'
        )

    @classmethod
    def params(cls, datasource, context):
        return {
        }

    @inlineCallbacks
    def collect(self, config):
        log.debug('Starting ESNode collect')

        ds0 = config.datasources[0]
        scheme = 'https' if ds0.zElasticSearchUseSSL else 'http'
        url = '{}://{}:{}/_nodes/stats'.format(scheme, config.id, ds0.zElasticSearchPort)

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

        data = self.new_data()
        for ds in config.datasources:
            comp_id = ds.component
            node_jvm_data = result['nodes'][comp_id]['jvm']
            node_jvm_mem_data = node_jvm_data['mem']
            data['values'][comp_id]['jvm_heap_used_bytes'] = node_jvm_mem_data['heap_used_in_bytes']
            data['values'][comp_id]['jvm_heap_committed_bytes'] = node_jvm_mem_data['heap_committed_in_bytes']
            data['values'][comp_id]['jvm_heap_max_bytes'] = node_jvm_mem_data['heap_max_in_bytes']
            data['values'][comp_id]['jvm_heap_used_perc'] = node_jvm_mem_data['heap_used_percent']
            data['values'][comp_id]['jvm_pool_young_used'] = node_jvm_mem_data['pools']['young']['used_in_bytes']
            data['values'][comp_id]['jvm_pool_young_max'] = node_jvm_mem_data['pools']['young']['max_in_bytes']
            data['values'][comp_id]['jvm_pool_old_used'] = node_jvm_mem_data['pools']['old']['used_in_bytes']
            data['values'][comp_id]['jvm_pool_old_max'] = node_jvm_mem_data['pools']['old']['max_in_bytes']
            data['values'][comp_id]['jvm_pool_survivor_used'] = node_jvm_mem_data['pools']['survivor']['used_in_bytes']
            data['values'][comp_id]['jvm_pool_survivor_max'] = node_jvm_mem_data['pools']['survivor']['max_in_bytes']
            data['values'][comp_id]['jvm_threads'] = node_jvm_data['threads']['count']
        return data

    def onError(self, result, config):
        log.error('Error - result is {}'.format(result))
        # TODO: send event of collection failure
        return {}
