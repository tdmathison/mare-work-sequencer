"""Trusted identifiers for shared research profile infrastructure."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ProfileType:
    key: str
    table: str
    stem: str
    path: str
    title: str
    singular: str
    tag_prefix: str

    @property
    def lower(self): return self.singular.lower()
    @property
    def osint_table(self): return self.stem + '_osint'
    @property
    def reports_table(self): return self.stem + '_reports'
    @property
    def foreign_key(self): return self.stem + '_id'
    @property
    def storage(self): return self.stem + '-reports'
    @property
    def staging(self): return self.stem + '-report-staging'
    @property
    def actor(self): return self.key == 'actors'

FAMILY = ProfileType('families','malware_families','family','/malware-families','Malware Families','Malware family','MAL_')
ACTOR = ProfileType('actors','threat_actors','actor','/threat-actors','Threat Actors','Threat actor','TA_')
