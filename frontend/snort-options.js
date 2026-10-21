// Curated documented choices. Profile variables/services still need configuration.
export const ACTIONS=['alert','block','drop','log','pass','react','reject','rewrite'];
export const PROTOCOLS=['ip','icmp','tcp','udp'];
export const SERVICES=['http','http2','ssl','dns','ftp','smtp','ssh','sip'];
export const ADDRESSES=['any','$HOME_NET','$EXTERNAL_NET','$HTTP_SERVERS','$SMTP_SERVERS','$DNS_SERVERS','$SQL_SERVERS','$TELNET_SERVERS','$SSH_SERVERS','$FTP_SERVERS','$SIP_SERVERS'];
export const PORTS=['any','$HTTP_PORTS','$SHELLCODE_PORTS','$ORACLE_PORTS','$SSH_PORTS','$FTP_PORTS','$SIP_PORTS','80','443','53','25','22'];
export const FLOW_GROUPS=[
 ['Direction',['to_server','to_client','from_client','from_server']],
 ['Connection state',['established','not_established','stateless']],
 ['Stream reassembly',['only_stream','no_stream']],
 ['Fragment reassembly',['only_frag','no_frag']]
];
export function flowTokens(value){return value.split(',').map(v=>v.trim()).filter(Boolean);}
export function validateFlow(value){
 const tokens=flowTokens(value),known=FLOW_GROUPS.flatMap(([,choices])=>choices);
 if(!tokens.length)throw Error('Choose at least one flow option, or remove the flow component.');
 if(tokens.some(t=>!known.includes(t)))throw Error('Unknown flow option. Review its spelling in Docs, or edit advanced syntax in source.');
 for(const [label,choices]of FLOW_GROUPS)if(tokens.filter(t=>choices.includes(t)).length>1)throw Error(`Choose only one ${label.toLowerCase()} option in flow.`);
 return tokens;
}
