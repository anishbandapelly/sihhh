const {withAndroidManifest}=require('@expo/config-plugins');
module.exports=config=>withAndroidManifest(config,config=>{const app=config.modResults.manifest.application[0];app.$['android:usesCleartextTraffic']=String((process.env.EXPO_PUBLIC_API_BASE_URL||'http://10.0.2.2:8000/api/v1').startsWith('http://'));return config});
