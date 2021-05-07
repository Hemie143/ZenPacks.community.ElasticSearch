"""
Models ElasticSearch components using API calls
"""

# stdlib Imports
import json
import base64
from datetime import datetime
from bs4 import BeautifulSoup

# Twisted Imports
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.client import Agent, readBody
from twisted.internet import reactor, ssl
from twisted.web.http_headers import Headers

# Zenoss Imports
from Products.DataCollector.plugins.CollectorPlugin import PythonPlugin
from Products.DataCollector.plugins.DataMaps import ObjectMap, RelationshipMap

from ZenPacks.community.ElasticSearch.lib.utils import SkipCertifContextFactory

class elasticsearch(PythonPlugin):

    requiredProperties = (
        'zElasticSearchUseSSL',
        'zElasticSearchPort',
    )

    deviceProperties = PythonPlugin.deviceProperties + requiredProperties

    @inlineCallbacks
    def collect(self, device, log):
        """Asynchronously collect data from device. Return a deferred/"""
        log.info('%s: collecting data', device.id)

        zElasticSearchPort = getattr(device, 'zElasticSearchPort', None)
        zElasticSearchUseSSL = getattr(device, 'zElasticSearchUseSSL', None)
        scheme = 'https' if zElasticSearchUseSSL else 'http'

        results = {}
        agent = Agent(reactor, contextFactory=SkipCertifContextFactory())
        headers = {
                   "Accept": ['application/json'],
                   }

        queries = {
            'cluster': '{}://{}:{}/_cluster/stats',
            'cluster_state': '{}://{}:{}/_cluster/state',
            'nodes': '{}://{}:{}/_nodes/stats',
        }

        for item, base_url in queries.items():
            try:
                url = base_url.format(scheme, device.id, zElasticSearchPort)
                log.debug('url: {}'.format(url))
                response = yield agent.request('GET', url, Headers(headers))
                response_body = yield readBody(response)
                response_body = json.loads(response_body)
                results[item] = response_body
            except Exception, e:
                log.error('%s: %s', device.id, e)

        returnValue(results)

    def process(self, device, results, log):
        # log.debug('results: {}'.format(results))
        rm = []

        if 'cluster' in results:
            rm.append(self.model_cluster(results['cluster'], log))
            if 'nodes' in results:
                rm.append(self.model_nodes(results['nodes'], log))
            if 'cluster_state' in results:
                rm.extend(self.model_indices(results['cluster_state'], log))

        log.debug('process rm: {}'.format(rm))
        return rm

    def model_cluster(self, data, log):
        log.debug('model_cluster data: {}'.format(data))
        om_cluster = ObjectMap()
        cluster_name = data['cluster_name']
        om_cluster.id = self.prepId(cluster_name)
        om_cluster.title = cluster_name
        om_cluster.uuid = data['cluster_uuid']
        return RelationshipMap(compname='',
                               relname='esclusters',
                               modname='ZenPacks.community.ElasticSearch.ESCluster',
                               objmaps=[om_cluster])

    def model_nodes(self, data, log):
        log.debug('model_nodes data: {}'.format(data))
        cluster_name = data['cluster_name']
        comp_cluster = 'esclusters/{}'.format(self.prepId(cluster_name))

        node_maps = []
        for node_id, node_data in data['nodes'].items():
            om_node = ObjectMap()
            om_node.id = self.prepId(node_id)
            om_node.title = '{} ({}) ({})'.format(node_data['name'], node_data['host'], node_id)
            om_node.name = node_data['name']
            om_node.host = node_data['host']
            om_node.ip = node_data['ip']
            node_maps.append(om_node)
        return RelationshipMap(compname=comp_cluster,
                               relname='esnodes',
                               modname='ZenPacks.community.ElasticSearch.ESNode',
                               objmaps=node_maps)

    def model_indices(self, data, log):
        # log.debug('model_indices data: {}'.format(data))
        cluster_name = data['cluster_name']
        comp_cluster = 'esclusters/{}'.format(self.prepId(cluster_name))

        rm = []
        rm_shards = []
        index_maps = []
        for index_id, index_data in data['metadata']['indices'].items():
            log.debug('model_indices index: {}'.format(index_id))
            om_index = ObjectMap()
            om_index.id = self.prepId(index_id)
            om_index.title = index_id
            index_maps.append(om_index)
            comp_index = '{}/esindices/{}'.format(comp_cluster, om_index.id)
            index_shards = data['routing_table']['indices'][index_id]['shards']
            log.debug('model_indices index_shards: {}'.format(index_shards))
            shards_maps = []
            for shard_id, shard_data in index_shards.items():
                log.debug('model_indices shard_id: {}'.format(shard_id))
                log.debug('model_indices shard_data: {}'.format(shard_data))
                om_shard = ObjectMap()
                om_shard.id = self.prepId('{}_{}'.format(index_id, shard_id))
                om_shard.title = '{}_{}'.format(index_id, shard_id)
                om_shard.primary = shard_data[0]['primary']
                om_shard.node = shard_data[0]['node']
                shards_maps.append(om_shard)
            rm_shards.append(RelationshipMap(compname=comp_index,
                                             relname='esshards',
                                             modname='ZenPacks.community.ElasticSearch.ESShard',
                                             objmaps=shards_maps))

        rm.append(RelationshipMap(compname=comp_cluster,
                                  relname='esindices',
                                  modname='ZenPacks.community.ElasticSearch.ESIndex',
                                  objmaps=index_maps))
        rm.extend(rm_shards)
        return rm
