export const declarationFields:Record<string,{key:string;label:string;numeric?:boolean}[]>={
D01:[{key:'common_generic_name',label:'Common / generic product name'}],
D02:[{key:'responsible_entity_name',label:'Manufacturer / packer / importer'},{key:'responsible_entity_address',label:'Address'},{key:'role_label',label:'Responsible entity role'}],
D03:[{key:'quantity_value',label:'Quantity',numeric:true},{key:'quantity_unit',label:'Unit'},{key:'quantity_kind',label:'MEASURE or COUNT'}],
D04:[{key:'mrp_amount',label:'MRP amount',numeric:true},{key:'currency',label:'Currency'},{key:'mrp_label',label:'Printed price label'}],
D05:[{key:'manufacture_month',label:'Month',numeric:true},{key:'manufacture_year',label:'Year',numeric:true}],
D06:[{key:'care_name_or_office',label:'Consumer care name / office'},{key:'care_address',label:'Consumer care address'},{key:'care_phone',label:'Telephone'},{key:'care_email',label:'Email'}]};
