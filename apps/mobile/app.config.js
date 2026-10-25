const { buildVariant } = require('./config/variants.cjs');

module.exports = ({ config }) => buildVariant(config);
