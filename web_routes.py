"""Web routes and templates for Meshtastic PingBot."""

import sqlite3
import csv
import io
from flask import request, jsonify, render_template_string, Response
from config import DATABASE_PATH, MAX_LOG_LINES


# HTML Templates
HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Meshtastic Ping-Pong Logs</title>
  <style>
    body { font-family: monospace; background: #1e1e1e; color: #eee; margin: 0; padding: 0; }
    .navbar { background: #2a2a2a; padding: 10px; border-bottom: 1px solid #444; }
    .navbar a { color: #00ff00; text-decoration: none; margin-right: 20px; padding: 5px 10px; }
    .navbar a:hover { background: #333; border-radius: 3px; }
    .navbar a.active { background: #444; border-radius: 3px; }
    h2 { margin: 10px; color: #00ff00; }
    #logs { height: 85vh; overflow-y: scroll; padding: 10px; box-sizing: border-box; background: #1e1e1e; }
    .log { margin: 0.2em 0; white-space: pre-wrap; }
    .cyan { color: #00ffff; }
    .green { color: #00ff00; }
    .yellow { color: #ffff00; }
    .red { color: #ff5555; }
    .magenta { color: #ff00ff; }
    .blue { color: #5555ff; }
    .bold { font-weight: bold; }
  </style>
</head>
<body>
  <div class="navbar">
    <a href="/" class="active">Live Logs</a>
    <a href="/nodes">Node Database</a>
    <a href="/health">Health</a>
  </div>
  <h2>Meshtastic Ping-Pong Logs</h2>
  <div id="logs"></div>
  <script src="//cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.4/socket.io.min.js"></script>
  <script>
    var socket = io();
    var logsDiv = document.getElementById("logs");
    var logLines = [];
    const MAX_LOG_LINES = {{ max_lines }};
    socket.on("log_message", function(data) {
      logLines.push(data);
      if (logLines.length > MAX_LOG_LINES) logLines.shift();
      logsDiv.innerHTML = logLines.join('');
      logsDiv.scrollTop = logsDiv.scrollHeight;
    });
  </script>
</body>
</html>
"""

HEALTH_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Meshtastic Pingbot - Health Status</title>
  <style>
    body { font-family: monospace; background: #1e1e1e; color: #eee; margin: 0; padding: 0; }
    .navbar { background: #2a2a2a; padding: 10px; border-bottom: 1px solid #444; }
    .navbar a { color: #00ff00; text-decoration: none; margin-right: 20px; padding: 5px 10px; }
    .navbar a:hover { background: #333; border-radius: 3px; }
    .navbar a.active { background: #444; border-radius: 3px; }
    .container { padding: 20px; }
    h2 { margin: 0 0 20px 0; color: #00ff00; }
    .status-card { background: #2a2a2a; border-radius: 8px; padding: 20px; margin-bottom: 20px; border-left: 4px solid #555; }
    .status-connected { border-left-color: #00ff00; }
    .status-disconnected { border-left-color: #ff5555; }
    .status-header { font-size: 1.2em; font-weight: bold; margin-bottom: 10px; }
    .status-value { font-size: 1.5em; margin-bottom: 15px; }
    .connected { color: #00ff00; }
    .disconnected { color: #ff5555; }
    .metric { margin-bottom: 8px; }
    .metric-label { color: #888; }
    .metric-value { color: #eee; font-weight: bold; }
    .refresh-btn { background: #00ff00; color: #000; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-weight: bold; }
    .refresh-btn:hover { background: #00cc00; }
    .timestamp { margin-top: 20px; color: #888; font-size: 0.9em; }
  </style>
</head>
<body>
  <div class="navbar">
    <a href="/">Live Logs</a>
    <a href="/nodes">Node Database</a>
    <a href="/health" class="active">Health</a>
  </div>
  <div class="container">
    <h2>Health Status</h2>
    
    <div class="status-card {{ 'status-connected' if connected else 'status-disconnected' }}">
      <div class="status-header">Connection Status</div>
      <div class="status-value {{ 'connected' if connected else 'disconnected' }}">
        {{ 'CONNECTED' if connected else 'DISCONNECTED' }}
      </div>
      <div class="metric">
        <span class="metric-label">Radio Link:</span>
        <span class="metric-value">{{ 'Active' if connected else 'Inactive' }}</span>
      </div>
    </div>
    
    <div class="status-card">
      <div class="status-header">Message Queue</div>
      <div class="metric">
        <span class="metric-label">Queued Messages:</span>
        <span class="metric-value">{{ queued }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">Queue Status:</span>
        <span class="metric-value">{{ 'Normal' if queued < 10 else 'High' if queued < 50 else 'Critical' }}</span>
      </div>
    </div>
    
    <button class="refresh-btn" onclick="window.location.reload()">Refresh Status</button>
    
    <div class="timestamp">
      Last updated: <span id="timestamp"></span>
    </div>
  </div>
  
  <script>
    document.getElementById('timestamp').textContent = new Date().toLocaleString();
    
    // Auto-refresh every 30 seconds
    setTimeout(function() {
      window.location.reload();
    }, 30000);
  </script>
</body>
</html>
"""

NODES_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Meshtastic Node Database</title>
  <style>
    body { font-family: monospace; background: #1e1e1e; color: #eee; margin: 0; padding: 0; }
    .navbar { background: #2a2a2a; padding: 10px; border-bottom: 1px solid #444; }
    .navbar a { color: #00ff00; text-decoration: none; margin-right: 20px; padding: 5px 10px; }
    .navbar a:hover { background: #333; border-radius: 3px; }
    .navbar a.active { background: #444; border-radius: 3px; }
    .container { padding: 20px; }
    h2 { color: #00ff00; margin-bottom: 20px; }
    
    .controls { background: #2a2a2a; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
    .controls input, .controls select { 
      background: #333; color: #eee; border: 1px solid #555; padding: 5px; margin-right: 10px; 
      border-radius: 3px; font-family: monospace;
    }
    .controls button { 
      background: #444; color: #eee; border: 1px solid #666; padding: 5px 10px; 
      border-radius: 3px; cursor: pointer; font-family: monospace;
    }
    .controls button:hover { background: #555; }
    
    .stats { color: #888; margin-bottom: 10px; }
    
    table { width: 100%; border-collapse: collapse; background: #2a2a2a; border-radius: 5px; overflow: hidden; }
    th, td { padding: 8px 12px; border-bottom: 1px solid #444; text-align: left; }
    th { background: #333; color: #00ff00; font-weight: bold; cursor: pointer; user-select: none; }
    th:hover { background: #444; }
    th.sortable::after { content: ' ↕'; opacity: 0.5; }
    th.sort-asc::after { content: ' ↑'; opacity: 1; color: #00ff00; }
    th.sort-desc::after { content: ' ↓'; opacity: 1; color: #00ff00; }
    
    tbody tr:hover { background: #333; }
    tbody tr.expanded { background: #2d2d2d; }
    .node-id { color: #00ffff; font-weight: bold; cursor: pointer; }
    .node-id:hover { text-decoration: underline; }
    .long-name { color: #00ff00; }
    .short-name { color: #ffff00; }
    .good-signal { color: #00ff00; }
    .fair-signal { color: #ffff00; }
    .poor-signal { color: #ff5555; }
    
    .details-row { display: none; }
    .details-row.show { display: table-row; }
    .details-cell { padding: 20px; background: #252525; border-left: 3px solid #00ff00; }
    .details-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }
    .detail-group { background: #2a2a2a; padding: 15px; border-radius: 5px; }
    .detail-group h4 { margin: 0 0 10px 0; color: #00ff00; font-size: 14px; }
    .detail-item { margin: 5px 0; font-size: 12px; }
    .detail-label { color: #888; display: inline-block; width: 180px; }
    .detail-value { color: #fff; }
    .detail-value.true { color: #00ff00; }
    .detail-value.false { color: #ff5555; }
    .detail-value.null { color: #888; font-style: italic; }
    
    .pagination { margin: 20px 0; text-align: center; }
    .pagination button { 
      background: #444; color: #eee; border: 1px solid #666; padding: 5px 10px; 
      margin: 0 2px; border-radius: 3px; cursor: pointer; 
    }
    .pagination button:hover:not(:disabled) { background: #555; }
    .pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
    .pagination .current { background: #00ff00; color: #000; }
    
    .badge { 
      display: inline-block; padding: 2px 6px; border-radius: 3px; 
      font-size: 10px; font-weight: bold; margin-left: 5px;
    }
    .badge-favorite { background: #ffaa00; color: #000; }
    .badge-licensed { background: #00aa00; color: #fff; }
  </style>
</head>
<body>
  <div class="navbar">
    <a href="/">Live Logs</a>
    <a href="/nodes" class="active">Node Database</a>
    <a href="/health">Health</a>
  </div>
  <div class="container">
    <h2>Node Database</h2>
    
    <div class="controls">
      <input type="text" id="searchInput" placeholder="Search nodes..." value="{{ search }}" />
      <button onclick="refreshData()">Search</button>
      <button onclick="exportData()">Export CSV</button>
      <button onclick="exportJSON()">Export JSON</button>
      <button onclick="refreshNodeDB()">Refresh NodeDB</button>
    </div>
    
    <div class="stats">
      Total nodes: {{ total_count }} | Page {{ page }} of {{ total_pages }} | Click a node ID to see all details
    </div>
    
    <table>
      <thead>
        <tr>
          <th class="sortable" data-column="node_id">Node ID</th>
          <th class="sortable" data-column="long_name">Long Name</th>
          <th class="sortable" data-column="short_name">Short</th>
          <th class="sortable" data-column="rssi">RSSI</th>
          <th class="sortable" data-column="snr">SNR</th>
          <th class="sortable" data-column="hops_away">Hops</th>
          <th class="sortable" data-column="battery_level">Batt</th>
          <th class="sortable" data-column="voltage">Volt</th>
          <th class="sortable" data-column="channel_utilization">Ch%</th>
          <th class="sortable" data-column="last_heard">Last Heard</th>
        </tr>
      </thead>
      <tbody>
        {% for node in nodes %}
        <tr onclick="toggleDetails('{{ node.node_id }}')">
          <td class="node-id">
            {{ node.node_id }}
            {% if node.is_favorite %}<span class="badge badge-favorite">★</span>{% endif %}
            {% if node.is_licensed %}<span class="badge badge-licensed">L</span>{% endif %}
          </td>
          <td class="long-name">{{ node.long_name or 'N/A' }}</td>
          <td class="short-name">{{ node.short_name or 'N/A' }}</td>
          <td class="{{ 'good-signal' if node.rssi and node.rssi > -80 else 'fair-signal' if node.rssi and node.rssi > -100 else 'poor-signal' }}">
            {{ node.rssi if node.rssi else 'N/A' }}
          </td>
          <td class="{{ 'good-signal' if node.snr and node.snr > 5 else 'fair-signal' if node.snr and node.snr > 0 else 'poor-signal' }}">
            {{ '%.1f' % node.snr if node.snr else 'N/A' }}
          </td>
          <td>{{ node.hops_away if node.hops_away is not none else 'N/A' }}</td>
          <td class="{{ 'good-signal' if node.battery_level and node.battery_level > 75 else 'fair-signal' if node.battery_level and node.battery_level > 25 else 'poor-signal' }}">
            {{ '%d%%' % node.battery_level if node.battery_level else 'N/A' }}
          </td>
          <td>{{ '%.2fV' % node.voltage if node.voltage else 'N/A' }}</td>
          <td>{{ '%.1f%%' % node.channel_utilization if node.channel_utilization else 'N/A' }}</td>
          <td>{{ node.last_heard | formatTimestamp if node.last_heard else 'Never' }}</td>
        </tr>
        <tr class="details-row" id="details-{{ node.node_id }}">
          <td colspan="10" class="details-cell">
            <div class="details-grid">
              <div class="detail-group">
                <h4>Node Information</h4>
                <div class="detail-item">
                  <span class="detail-label">Node Number:</span>
                  <span class="detail-value">{{ node.node_num if node.node_num else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">MAC Address:</span>
                  <span class="detail-value">{{ node.mac_addr if node.mac_addr else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Hardware Model:</span>
                  <span class="detail-value">{{ node.hw_model if node.hw_model else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Role:</span>
                  <span class="detail-value">{{ node.role if node.role else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Public Key:</span>
                  <span class="detail-value" style="font-size: 10px; word-break: break-all;">{{ node.public_key[:40] + '...' if node.public_key and node.public_key|length > 40 else (node.public_key if node.public_key else 'N/A') }}</span>
                </div>
              </div>
              
              <div class="detail-group">
                <h4>Network Metrics</h4>
                <div class="detail-item">
                  <span class="detail-label">RSSI:</span>
                  <span class="detail-value">{{ node.rssi if node.rssi else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">SNR:</span>
                  <span class="detail-value">{{ '%.2f' % node.snr if node.snr else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Hop Count:</span>
                  <span class="detail-value">{{ node.hop_count if node.hop_count else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Hops Away:</span>
                  <span class="detail-value">{{ node.hops_away if node.hops_away is not none else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Via MQTT:</span>
                  <span class="detail-value {{ 'true' if node.via_mqtt else 'false' }}">{{ 'Yes' if node.via_mqtt else 'No' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Is Favorite:</span>
                  <span class="detail-value {{ 'true' if node.is_favorite else 'false' }}">{{ 'Yes' if node.is_favorite else 'No' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Is Licensed:</span>
                  <span class="detail-value {{ 'true' if node.is_licensed else 'false' }}">{{ 'Yes' if node.is_licensed else 'No' }}</span>
                </div>
              </div>
              
              <div class="detail-group">
                <h4>Device Metrics</h4>
                <div class="detail-item">
                  <span class="detail-label">Battery Level:</span>
                  <span class="detail-value">{{ '%d%%' % node.battery_level if node.battery_level else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Voltage:</span>
                  <span class="detail-value">{{ '%.3fV' % node.voltage if node.voltage else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Channel Utilization:</span>
                  <span class="detail-value">{{ '%.2f%%' % node.channel_utilization if node.channel_utilization else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Air Util TX:</span>
                  <span class="detail-value">{{ '%.2f%%' % node.air_util_tx if node.air_util_tx else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Uptime:</span>
                  <span class="detail-value">{{ formatUptime(node.uptime_seconds) if node.uptime_seconds else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Temperature:</span>
                  <span class="detail-value">{{ '%.1f°C' % node.temperature if node.temperature else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Humidity:</span>
                  <span class="detail-value">{{ '%.1f%%' % node.humidity if node.humidity else 'N/A' }}</span>
                </div>
              </div>
              
              <div class="detail-group">
                <h4>Position Data</h4>
                <div class="detail-item">
                  <span class="detail-label">Latitude:</span>
                  <span class="detail-value">{{ '%.6f' % node.latitude if node.latitude else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Longitude:</span>
                  <span class="detail-value">{{ '%.6f' % node.longitude if node.longitude else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Altitude:</span>
                  <span class="detail-value">{{ '%dm' % node.altitude if node.altitude else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Position Time:</span>
                  <span class="detail-value">{{ node.position_time | formatTimestamp if node.position_time else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Location Source:</span>
                  <span class="detail-value">{{ node.position_location_source if node.position_location_source else 'N/A' }}</span>
                </div>
              </div>
              
              <div class="detail-group">
                <h4>Timestamps</h4>
                <div class="detail-item">
                  <span class="detail-label">Last Heard:</span>
                  <span class="detail-value">{{ node.last_heard | formatTimestamp if node.last_heard else 'Never' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Created At:</span>
                  <span class="detail-value">{{ node.created_at | formatTimestamp if node.created_at else 'N/A' }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Updated At:</span>
                  <span class="detail-value">{{ node.updated_at | formatTimestamp if node.updated_at else 'N/A' }}</span>
                </div>
              </div>
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    
    <div class="pagination">
      {% if page > 1 %}
        <button onclick="changePage({{ page - 1 }})">Previous</button>
      {% endif %}
      
      {% for p in range(1, total_pages + 1) %}
        {% if p == page %}
          <button class="current" disabled>{{ p }}</button>
        {% elif p <= 3 or p >= total_pages - 2 or (p >= page - 2 and p <= page + 2) %}
          <button onclick="changePage({{ p }})">{{ p }}</button>
        {% elif p == 4 and page > 6 %}
          <span>...</span>
        {% elif p == total_pages - 3 and page < total_pages - 5 %}
          <span>...</span>
        {% endif %}
      {% endfor %}
      
      {% if page < total_pages %}
        <button onclick="changePage({{ page + 1 }})">Next</button>
      {% endif %}
    </div>
  </div>
  
  <script>
    let currentSort = '{{ sort_by }}';
    let currentOrder = '{{ sort_order }}';
    let currentSearch = '{{ search }}';
    
    function formatUptime(seconds) {
      if (!seconds) return 'N/A';
      const days = Math.floor(seconds / 86400);
      const hours = Math.floor((seconds % 86400) / 3600);
      const mins = Math.floor((seconds % 3600) / 60);
      return days + 'd ' + hours + 'h ' + mins + 'm';
    }
    
    function toggleDetails(nodeId) {
      const detailsRow = document.getElementById('details-' + nodeId);
      if (detailsRow.classList.contains('show')) {
        detailsRow.classList.remove('show');
      } else {
        // Close all other details rows
        document.querySelectorAll('.details-row.show').forEach(row => {
          row.classList.remove('show');
        });
        detailsRow.classList.add('show');
      }
    }
    
    function changePage(page) {
      const params = new URLSearchParams({
        page: page,
        sort: currentSort,
        order: currentOrder,
        search: currentSearch
      });
      window.location.href = '/nodes?' + params.toString();
    }
    
    function sortTable(column) {
      if (currentSort === column) {
        currentOrder = currentOrder === 'asc' ? 'desc' : 'asc';
      } else {
        currentSort = column;
        currentOrder = 'desc';
      }
      
      const params = new URLSearchParams({
        sort: currentSort,
        order: currentOrder,
        search: currentSearch
      });
      
      window.location.href = '/nodes?' + params.toString();
    }
    
    function refreshData() {
      currentSearch = document.getElementById('searchInput').value;
      const params = new URLSearchParams({
        sort: currentSort,
        order: currentOrder,
        search: currentSearch
      });
      
      window.location.href = '/nodes?' + params.toString();
    }
    
    function refreshNodeDB() {
      fetch('/nodedb/refresh', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
          alert(data.message || 'NodeDB refresh completed');
          window.location.reload();
        })
        .catch(error => {
          alert('Error refreshing NodeDB: ' + error);
        });
    }
    
    function updateSortHeaders() {
      document.querySelectorAll('th.sortable').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (th.dataset.column === currentSort) {
          th.classList.add('sort-' + currentOrder);
        }
      });
    }
    
    function exportData() {
      const params = new URLSearchParams({
        sort: currentSort,
        order: currentOrder,
        search: currentSearch,
        export: 'csv'
      });
      
      window.open('/nodes/export?' + params.toString());
    }
    
    function exportJSON() {
      window.open('/nodes/export?format=json');
    }
    
    // Initialize
    document.addEventListener('DOMContentLoaded', function() {
      updateSortHeaders();
      
      // Add click handlers for sortable headers
      document.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', () => sortTable(th.dataset.column));
      });
      
      // Add enter key handler for search
      document.getElementById('searchInput').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
          refreshData();
        }
      });
      
      // Auto-refresh every 30 seconds
      setInterval(() => window.location.reload(), 30000);
    });
  </script>
</body>
</html>
"""


def setup_routes(app, is_connected_func, message_queue_count_func, enhanced_download_nodedb_func):
    """Setup Flask routes for the application."""
    
    @app.route("/")
    def index():
        return render_template_string(HTML_TEMPLATE, max_lines=MAX_LOG_LINES)

    @app.route("/nodes")
    def nodes():
        """Database browser for nodes"""
        # Get query parameters for filtering and sorting
        sort_by = request.args.get('sort', 'updated_at')
        sort_order = request.args.get('order', 'desc')
        search = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        # Validate sort parameters
        valid_columns = ['node_id', 'long_name', 'short_name', 'rssi', 'snr', 'hop_count', 'hops_away', 
                        'last_heard', 'updated_at', 'battery_level', 'voltage', 'channel_utilization']
        if sort_by not in valid_columns:
            sort_by = 'updated_at'
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'
        
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Build query with search filter - include all fields
            base_query = '''
                SELECT node_id, node_num, long_name, short_name, mac_addr, hw_model, role, 
                       public_key, last_heard, snr, rssi, hop_count, hops_away, is_licensed, 
                       is_favorite, via_mqtt, created_at, updated_at, temperature, humidity, 
                       voltage, battery_level, channel_utilization, air_util_tx, uptime_seconds,
                       latitude, longitude, altitude, position_time, position_location_source
                FROM nodes
            '''
            
            where_clause = ""
            params = []
            
            if search:
                where_clause = """
                    WHERE (node_id LIKE ? OR long_name LIKE ? OR short_name LIKE ?)
                """
                search_param = f"%{search}%"
                params = [search_param, search_param, search_param]
            
            # Add sorting
            order_clause = f" ORDER BY {sort_by} {sort_order.upper()}"
            
            # Count total records
            count_query = f"SELECT COUNT(*) FROM nodes{where_clause}"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            
            # Add pagination
            limit_clause = f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"
            
            # Execute main query
            full_query = base_query + where_clause + order_clause + limit_clause
            cursor.execute(full_query, params)
            
            nodes_data = []
            for row in cursor.fetchall():
                node_data = {
                    'node_id': row[0],
                    'node_num': row[1],
                    'long_name': row[2],
                    'short_name': row[3],
                    'mac_addr': row[4],
                    'hw_model': row[5],
                    'role': row[6],
                    'public_key': row[7],
                    'last_heard': row[8],
                    'snr': row[9],
                    'rssi': row[10],
                    'hop_count': row[11],
                    'hops_away': row[12],
                    'is_licensed': row[13],
                    'is_favorite': row[14],
                    'via_mqtt': row[15],
                    'created_at': row[16],
                    'updated_at': row[17],
                    'temperature': row[18],
                    'humidity': row[19],
                    'voltage': row[20],
                    'battery_level': row[21],
                    'channel_utilization': row[22],
                    'air_util_tx': row[23],
                    'uptime_seconds': row[24],
                    'latitude': row[25],
                    'longitude': row[26],
                    'altitude': row[27],
                    'position_time': row[28],
                    'position_location_source': row[29]
                }
                nodes_data.append(node_data)
            
            conn.close()
            
            # Calculate pagination info
            total_pages = (total_count + per_page - 1) // per_page
            
            # If this is an AJAX request, return JSON
            if request.headers.get('Accept') == 'application/json':
                return jsonify({
                    'nodes': nodes_data,
                    'total_count': total_count,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': total_pages,
                    'sort_by': sort_by,
                    'sort_order': sort_order,
                    'search': search
                })
            
            # Otherwise return HTML template
            return render_template_string(NODES_TEMPLATE, 
                                        nodes=nodes_data,
                                        total_count=total_count,
                                        page=page,
                                        per_page=per_page,
                                        total_pages=total_pages,
                                        sort_by=sort_by,
                                        sort_order=sort_order,
                                        search=search)
        
        except Exception as e:
            if request.headers.get('Accept') == 'application/json':
                return jsonify({'error': str(e)}), 500
            return f"Database error: {e}", 500

    @app.route("/nodes/export")
    def export_nodes():
        """Export nodes data as CSV or JSON"""
        format_type = request.args.get('format', 'csv').lower()
        
        try:
            # Get same parameters as nodes route for consistency
            sort_by = request.args.get('sort', 'updated_at')
            sort_order = request.args.get('order', 'desc')
            search = request.args.get('search', '')
            
            # Validate sort parameters
            valid_columns = ['node_id', 'long_name', 'short_name', 'rssi', 'snr', 'hop_count', 'hops_away',
                            'last_heard', 'updated_at', 'battery_level', 'voltage', 'channel_utilization']
            if sort_by not in valid_columns:
                sort_by = 'updated_at'
            if sort_order not in ['asc', 'desc']:
                sort_order = 'desc'
            
            # Export as JSON if requested
            if format_type == 'json':
                from database import export_nodedb_to_json
                json_data = export_nodedb_to_json()
                if json_data:
                    return Response(
                        json_data,
                        mimetype='application/json',
                        headers={'Content-Disposition': 'attachment; filename=meshtastic_nodes.json'}
                    )
                else:
                    return jsonify({'error': 'Failed to export nodedb'}), 500
            
            # Export as CSV (default) - include all fields
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Build query (no pagination for export) - include all fields
            base_query = '''
                SELECT node_id, node_num, long_name, short_name, mac_addr, hw_model, role, 
                       public_key, last_heard, snr, rssi, hop_count, hops_away, is_licensed, 
                       is_favorite, via_mqtt, created_at, updated_at, temperature, humidity, 
                       voltage, battery_level, channel_utilization, air_util_tx, uptime_seconds,
                       latitude, longitude, altitude, position_time, position_location_source
                FROM nodes
            '''
            
            where_clause = ""
            params = []
            
            if search:
                where_clause = """
                    WHERE (node_id LIKE ? OR long_name LIKE ? OR short_name LIKE ?)
                """
                search_param = f"%{search}%"
                params = [search_param, search_param, search_param]
            
            # Add sorting
            order_clause = f" ORDER BY {sort_by} {sort_order.upper()}"
            
            # Execute query
            full_query = base_query + where_clause + order_clause
            cursor.execute(full_query, params)
            
            # Create CSV content
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header - all fields
            writer.writerow([
                'Node ID', 'Node Num', 'Long Name', 'Short Name', 'MAC Address', 'HW Model', 'Role',
                'Public Key', 'Last Heard', 'SNR', 'RSSI', 'Hop Count', 'Hops Away', 'Licensed', 
                'Favorite', 'Via MQTT', 'Created At', 'Updated At', 'Temperature', 'Humidity', 
                'Voltage', 'Battery Level', 'Channel Util', 'Air Util TX', 'Uptime Seconds',
                'Latitude', 'Longitude', 'Altitude', 'Position Time', 'Location Source'
            ])
            
            # Write data rows
            for row in cursor.fetchall():
                writer.writerow(row)
            
            conn.close()
            
            # Return CSV as downloadable file
            output.seek(0)
            return Response(
                output.getvalue(),
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=meshtastic_nodes.csv'}
            )
            
        except Exception as e:
            return f"Export error: {e}", 500

    @app.route("/health")
    def health():
        """Health check endpoint"""
        health_data = {
            "connected": is_connected_func(),
            "queued": message_queue_count_func()
        }
        
        # If this is an API request (Accept: application/json), return JSON
        if request.headers.get('Accept') == 'application/json':
            response = jsonify(health_data)
            response.headers['Content-Type'] = 'application/json'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            return response
        
        # Otherwise return HTML template for web interface
        return render_template_string(HEALTH_TEMPLATE, 
                                    connected=health_data["connected"],
                                    queued=health_data["queued"])

    @app.route("/nodedb/stats")
    def nodedb_stats():
        """NodeDB statistics endpoint"""
        from database import get_nodedb_statistics
        
        stats = get_nodedb_statistics()
        if not stats:
            return jsonify({'error': 'Failed to get statistics'}), 500
        
        # Add connection status
        stats['connected'] = is_connected_func()
        
        # If this is an API request, return JSON
        if request.headers.get('Accept') == 'application/json':
            return jsonify(stats)
        
        # Otherwise return plain text for simple monitoring
        return f"""NodeDB Statistics:
Total Nodes: {stats['total_nodes']}
Complete Nodes: {stats['complete_nodes']} ({stats['completion_rate']:.1f}%)
Recent Nodes (24h): {stats['recent_nodes']}
Nodes with Location: {stats['nodes_with_location']}
Connected: {stats['connected']}"""

    @app.route("/nodedb/refresh", methods=['POST'])
    def nodedb_refresh():
        """Manually trigger nodedb refresh"""
        try:
            if not is_connected_func():
                return jsonify({'error': 'Radio not connected'}), 503
            
            # Trigger enhanced nodedb download
            success = enhanced_download_nodedb_func()
            
            if success:
                return jsonify({'message': 'NodeDB refresh completed successfully'})
            else:
                return jsonify({'error': 'NodeDB refresh failed'}), 500
                
        except Exception as e:
            return jsonify({'error': f'NodeDB refresh error: {str(e)}'}), 500

    @app.route("/nodedb/import", methods=['POST'])
    def nodedb_import():
        """Import nodes from JSON data (similar to meshtastic --info json output)"""
        try:
            # Check if JSON data was provided
            if not request.json:
                return jsonify({'error': 'No JSON data provided'}), 400
            
            from database import import_nodedb_from_json
            
            # Import the nodes
            success = import_nodedb_from_json(request.json)
            
            if success:
                return jsonify({'message': 'NodeDB import completed successfully'})
            else:
                return jsonify({'error': 'NodeDB import failed'}), 500
                
        except Exception as e:
            return jsonify({'error': f'NodeDB import error: {str(e)}'}), 500

    @app.after_request
    def add_security_headers(response):
        """Add basic security headers"""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response