window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, latlng, context) {
                var stageColors = {
                    1: '#D97706',
                    2: '#DC2626',
                    3: '#059669',
                    4: '#7C3AED'
                };
                var color = stageColors[feature.properties.stage_num] || '#78716C';
                var shortLabels = {
                    1: 'NOD',
                    2: 'NTS',
                    3: 'NOR',
                    4: 'TDUS'
                };
                var label = shortLabels[feature.properties.stage_num] || '';
                var size = 28;
                var icon = L.divIcon({
                    className: '',
                    html: '<div style="width:' + size + 'px;height:' + size + 'px;' +
                        'border-radius:50% 50% 50% 0;transform:rotate(-45deg);' +
                        'background:' + color + ';border:2px solid rgba(255,255,255,0.95);' +
                        'box-shadow:0 2px 6px rgba(0,0,0,0.28);' +
                        'display:flex;align-items:center;justify-content:center;">' +
                        '<span style="transform:rotate(45deg);font-size:6px;font-weight:700;' +
                        'color:#fff;font-family:sans-serif;letter-spacing:-0.5px">' + label + '</span>' +
                        '</div>',
                    iconSize: [size, size],
                    iconAnchor: [size / 2, size],
                    popupAnchor: [0, -size],
                });
                return L.marker(latlng, {
                    icon: icon
                });
            }

            ,
        function1: function(feature, layer, context) {
            var p = feature.properties;
            var stageColors = {
                1: '#D97706',
                2: '#DC2626',
                3: '#059669',
                4: '#7C3AED'
            };
            var color = stageColors[p.stage_num] || '#78716C';
            var tip = '<div style="font-family:system-ui;min-width:160px">';
            tip += '<div style="font-weight:600;font-size:13px;margin-bottom:3px">' + (p.address || 'Unknown') + '</div>';
            tip += '<span style="color:' + color + ';font-weight:700;font-size:11px">' + (p.stage_short || '') + '</span>';
            if (p.county) tip += '<span style="color:#78716C;font-size:11px"> &middot; ' + p.county + '</span>';
            if (p.emv) tip += '<div style="font-size:11px;color:#44403C;margin-top:2px">EMV: ' + p.emv + '</div>';
            if (p.timeline && p.timeline.length > 1)
                tip += '<div style="font-size:10px;color:#A8A29E;margin-top:2px">' + p.timeline.length + ' filings</div>';
            tip += '</div>';
            layer.bindTooltip(tip, {
                sticky: true,
                direction: 'top',
                offset: [0, -6],
                className: 'dca-map-tooltip'
            });
        }

    }
});