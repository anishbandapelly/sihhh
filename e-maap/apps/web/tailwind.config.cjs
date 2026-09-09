const tokens=require('../../shared/design-tokens/tokens.json');
module.exports={content:['./src/**/*.{ts,tsx}'],theme:{extend:{colors:tokens.colors,borderRadius:{panel:'8px'}}},plugins:[]};
