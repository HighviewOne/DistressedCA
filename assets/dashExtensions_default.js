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
            var popup = '<div style="min-width:240px;font-size:0.85rem;line-height:1.6">';

            // Header: address + stage badge
            popup += '<b style="font-size:0.95rem">' + (p.address || 'Address unknown') + '</b><br>';
            if (p.city) popup += p.city + (p.zip ? '&nbsp;' + p.zip : '') + '<br>';
            popup += '<span style="background:' + p.color + ';color:#fff;padding:1px 7px;border-radius:3px;font-size:0.75rem;font-weight:bold">' + (p.stage_short || '') + '</span>';
            if (p.county) popup += ' <span style="font-size:0.8rem;color:#555">' + p.county + '</span>';
            popup += '<br>';

            // Auction block (NTS only)
            if (p.sale_date) {
                popup += '<div style="margin:6px 0;padding:6px 8px;background:#fff1f1;border-left:3px solid #ef4444;border-radius:2px">';
                popup += '<b style="color:#ef4444">&#127942; Auction: ' + p.sale_date;
                if (p.sale_time) popup += ' at ' + p.sale_time;
                popup += '</b>';
                if (p.auction_location) popup += '<br><span style="font-size:0.78rem">' + p.auction_location + '</span>';
                if (p.min_bid) popup += '<br>Min Bid: <b>' + p.min_bid + '</b>';
                popup += '</div>';
            }

            // Financial row
            popup += 'Loan: <b>' + (p.loan_amount || 'N/A') + '</b>';
            if (p.ltv) popup += ' &nbsp;LTV: <b>' + p.ltv + '</b>';
            if (p.emv) popup += ' &nbsp;EMV: ' + p.emv;
            popup += '<br>';

            if (p.default_amount) popup += 'Default Amt: <b>' + p.default_amount + '</b><br>';
            popup += 'Recorded: ' + (p.recording_date || '') + '<br>';
            if (p.borrower) popup += 'Borrower: ' + p.borrower + '<br>';

            // Property details
            if (p.beds || p.baths || p.sqft || p.year_built) {
                var details = [];
                if (p.beds) details.push(p.beds + ' bd');
                if (p.baths) details.push(p.baths + ' ba');
                if (p.sqft) details.push(p.sqft + ' sqft');
                if (p.year_built) details.push('Built ' + p.year_built);
                popup += details.join(' &middot; ') + '<br>';
            }
            if (p.assessed_total) popup += 'Assessed: ' + p.assessed_total + '<br>';

            // Trustee / beneficiary
            if (p.trustee_name && p.trustee_name !== p.trustee) {
                popup += 'Trustee: ' + p.trustee_name;
                if (p.trustee_phone) popup += ' <a href="tel:' + p.trustee_phone + '">' + p.trustee_phone + '</a>';
                popup += '<br>';
            } else if (p.trustee) {
                popup += 'Trustee: ' + p.trustee + '<br>';
            }
            if (p.beneficiary) {
                popup += 'Lender: ' + p.beneficiary;
                if (p.ben_phone) popup += ' <a href="tel:' + p.ben_phone + '">' + p.ben_phone + '</a>';
                popup += '<br>';
            }

            // Badges
            var badges = '';
            if (p.hard_money === 'Yes') badges += '<span style="background:#fbbf24;color:#000;padding:1px 5px;border-radius:3px;font-size:0.7rem;margin-right:3px">Hard Money</span>';
            if (p.corporate === 'Yes') badges += '<span style="background:#6b7280;color:#fff;padding:1px 5px;border-radius:3px;font-size:0.7rem;margin-right:3px">Corporate</span>';
            if (p.source === 'RETRAN') badges += '<span style="background:#3b82f6;color:#fff;padding:1px 5px;border-radius:3px;font-size:0.7rem">RETRAN</span>';
            if (badges) popup += badges + '<br>';

            if (p.source_url) popup += '<a href="' + p.source_url + '" target="_blank" rel="noopener noreferrer" style="font-size:0.8rem">View County Record ↗</a>';
            popup += '</div>';
            layer.bindPopup(popup, {
                maxWidth: 300
            });
            layer.bindTooltip(p.address || 'Click for details', {
                sticky: true,
                direction: 'top',
                offset: [0, -5]
            });
        }

    }
});