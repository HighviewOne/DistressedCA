window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, latlng, context) {
                var stageColors = {
                    1: '#f59e0b',
                    2: '#ef4444',
                    3: '#22c55e',
                    4: '#7c3aed'
                };
                var color = stageColors[feature.properties.stage_num] || '#6b7280';
                return L.circleMarker(latlng, {
                    radius: 7,
                    fillColor: color,
                    color: '#fff',
                    weight: 1.5,
                    opacity: 1,
                    fillOpacity: 0.85
                });
            }

            ,
        function1: function(feature, layer, context) {
            var p = feature.properties;
            var tip = '<b style="font-size:0.85rem">' + (p.address || 'Unknown') + '</b><br>';
            tip += '<span style="color:' + p.color + ';font-weight:bold">' + (p.stage_short || '') + '</span>';
            if (p.county) tip += ' &middot; ' + p.county;
            if (p.timeline && p.timeline.length > 1)
                tip += '<br><span style="font-size:0.75rem;color:#9ca3af">' + p.timeline.length + ' filings — click for timeline</span>';
            layer.bindTooltip(tip, {
                sticky: true,
                direction: 'top',
                offset: [0, -5]
            });
        }

    }
});