"""Pinned official MISP conversion behind MARE's row/identity contract.

The protected custom-attribute hook is the upstream fallback, not a new object
format. Its contract is regression-tested against misp-stix 2026.10.12.
"""
import json
import re
import uuid
from datetime import datetime
from misp_stix_converter import MISPtoSTIX21Parser
from pymisp import MISPEvent
from stix2 import parse


class ContextParser(MISPtoSTIX21Parser):
    def __init__(self,value,description):
        super().__init__();self.literal_value=value;self.literal_description=description

    def _load_misp_event(self,event,errors):
        # Central validation has already checked the row. Loading the catalog-backed
        # model here also covers catalog entries missing in PyMISP's validator switch.
        model=MISPEvent();model.from_dict(**event['Event']);return model

    def _resolve_attribute(self, attribute):
        # Validation has already run on the official event model. Restore literal
        # content before the upstream writer so whitespace-only text is not lost.
        attribute.value=self.literal_value
        attribute.comment=self.literal_description
        self._parse_custom_attribute(attribute)


def convert_attribute(kind,value,description,meta,category,*,native=False,to_ids=False,pattern=None,components=None,native_type=None):
    """Convert a proper single-attribute event, retaining only its primary SDO.

    The table contains no observation evidence, so auxiliary Observed Data/SCOs
    manufactured from an attribute timestamp are deliberately not published.
    """
    row_uuid=meta['id'].split('--')[1]
    clock=datetime.fromisoformat(meta['modified'].replace('Z','+00:00'))
    event={'uuid':str(uuid.uuid5(uuid.UUID(row_uuid),'conversion-event')),
           'info':'MARE indicator conversion','timestamp':int(clock.timestamp()),
           'date':clock.date().isoformat(),'published':False,
           'Orgc':{'uuid':str(uuid.uuid5(uuid.NAMESPACE_URL,'mare:conversion-adapter')),'name':'MARE conversion adapter'},
           'Attribute':[{'uuid':row_uuid,'type':kind,'value':value,'comment':description,
                         'category':category,'timestamp':int(clock.timestamp()),'to_ids':to_ids}]}
    converter=MISPtoSTIX21Parser() if native else ContextParser(value,description)
    converter.parse_misp_event({'Event':event})
    if converter.errors:
        raise ValueError(f'Official MISP conversion failed for {kind}; correct the value or required content.')
    wanted=((native_type or 'indicator') if native else 'x-misp-attribute')+'--'+row_uuid
    primary=[obj for obj in converter.stix_objects if obj.id==wanted]
    if len(primary)!=1:raise ValueError(f'Official converter did not produce a faithful {kind} attribute; no partial export was published.')
    result=json.loads(primary[0].serialize())
    result.pop('created_by_ref',None)  # the internal technical model is not a source organization
    result['created']=meta['created'];result['modified']=meta['modified']
    result['labels']=[label for label in result.get('labels',[]) if not label.startswith('misp:to_ids=')]
    result['labels'].append('misp:to_ids="'+str(to_ids)+'"')
    if 'original_type' in meta:result['labels'].append('mare:original-type='+json.dumps(meta['original_type']))
    if native:
        if pattern is not None:result['pattern']=pattern  # shared validated/refanged components
        elif components is not None:
            # Retain upstream field syntax: its importer is stricter than the
            # STIX grammar about quoted property names. Replace equality literals
            # only, with independently validated/refanged component values.
            expression=r"(=\s*)'(?:\\.|[^'\\])*'"
            if len(re.findall(expression,result['pattern']))!=len(components):raise ValueError(f'Native {kind} pattern structure changed; review the pinned converter mapping.')
            values=iter(components)
            def replace(match):
                value=next(values)
                return match[1]+"'"+value.replace('\\','\\\\').replace("'","\\'")+"'"
            result['pattern']=re.sub(expression,replace,result['pattern'])
        if result['type']=='indicator':result['valid_from']=meta['created']
        if description:result['description']=description
    else:
        # PyMISP strips boundary whitespace while building its model. The STIX
        # envelope must retain the actual analyst text, even though a subsequent
        # MISP import may trim it again (documented upstream limitation).
        result['x_misp_value']=value
        result['x_misp_to_ids']=to_ids
        if description:result['x_misp_comment']=description
    return parse(result,version='2.1',allow_custom=True)
