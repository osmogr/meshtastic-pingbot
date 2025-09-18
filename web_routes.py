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
    .node-id { color: #00ffff; font-weight: bold; }
    .long-name { color: #00ff00; }
    .short-name { color: #ffff00; }
    .good-signal { color: #00ff00; }
    .fair-signal { color: #ffff00; }
    .poor-signal { color: #ff5555; }
    .pagination { margin: 20px 0; text-align: center; }
    .pagination button { 
      background: #444; color: #eee; border: 1px solid #666; padding: 5px 10px; 
      margin: 0 2px; border-radius: 3px; cursor: pointer; 
    }
    .pagination button:hover:not(:disabled) { background: #555; }
    .pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
    .pagination .current { background: #00ff00; color: #000; }
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
      <button onclick="refreshNodeDB()">Refresh NodeDB</button>
    </div>
    
    <div class="stats">
      Total nodes: {{ total_count }} | Page {{ page }} of {{ total_pages }}
    </div>
    
    <table>
      <thead>
        <tr>
          <th class="sortable" data-column="node_id">Node ID</th>
          <th class="sortable" data-column="long_name">Long Name</th>
          <th class="sortable" data-column="short_name">Short Name</th>
          <th class="sortable" data-column="rssi">RSSI</th>
          <th class="sortable" data-column="snr">SNR</th>
          <th class="sortable" data-column="hop_count">Hops</th>
          <th class="sortable" data-column="last_heard">Last Heard</th>
          <th class="sortable" data-column="updated_at">Updated</th>
        </tr>
      </thead>
      <tbody>
        {% for node in nodes %}
        <tr>
          <td class="node-id">{{ node.node_id }}</td>
          <td class="long-name">{{ node.long_name or 'N/A' }}</td>
          <td class="short-name">{{ node.short_name or 'N/A' }}</td>
          <td class="{{ 'good-signal' if node.rssi and node.rssi > -80 else 'fair-signal' if node.rssi and node.rssi > -100 else 'poor-signal' }}">
            {{ node.rssi if node.rssi else 'N/A' }}
          </td>
          <td class="{{ 'good-signal' if node.snr and node.snr > 5 else 'fair-signal' if node.snr and node.snr > 0 else 'poor-signal' }}">
            {{ node.snr if node.snr else 'N/A' }}
          </td>
          <td>{{ node.hop_count if node.hop_count else 'N/A' }}</td>
          <td>{{ node.last_heard | formatTimestamp if node.last_heard else 'Never' }}</td>
          <td>{{ node.updated_at | formatTimestamp if node.updated_at else 'Never' }}</td>
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
        valid_columns = ['node_id', 'long_name', 'short_name', 'rssi', 'snr', 'hop_count', 'last_heard', 'updated_at']
        if sort_by not in valid_columns:
            sort_by = 'updated_at'
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'
        
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Build query with search filter
            base_query = '''
                SELECT node_id, long_name, short_name, mac_addr, hw_model, role, 
                       last_heard, snr, rssi, hop_count, is_licensed, via_mqtt, 
                       created_at, updated_at
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
                    'long_name': row[1],
                    'short_name': row[2],
                    'mac_addr': row[3],
                    'hw_model': row[4],
                    'role': row[5],
                    'last_heard': row[6],
                    'snr': row[7],
                    'rssi': row[8],
                    'hop_count': row[9],
                    'is_licensed': row[10],
                    'via_mqtt': row[11],
                    'created_at': row[12],
                    'updated_at': row[13]
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
        """Export nodes data as CSV"""
        try:
            # Get same parameters as nodes route for consistency
            sort_by = request.args.get('sort', 'updated_at')
            sort_order = request.args.get('order', 'desc')
            search = request.args.get('search', '')
            
            # Validate sort parameters
            valid_columns = ['node_id', 'long_name', 'short_name', 'rssi', 'snr', 'hop_count', 'last_heard', 'updated_at']
            if sort_by not in valid_columns:
                sort_by = 'updated_at'
            if sort_order not in ['asc', 'desc']:
                sort_order = 'desc'
            
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Build query (no pagination for export)
            base_query = '''
                SELECT node_id, long_name, short_name, mac_addr, hw_model, role, 
                       last_heard, snr, rssi, hop_count, is_licensed, via_mqtt, 
                       created_at, updated_at
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
            
            # Write header
            writer.writerow([
                'Node ID', 'Long Name', 'Short Name', 'MAC Address', 'HW Model', 'Role',
                'Last Heard', 'SNR', 'RSSI', 'Hop Count', 'Licensed', 'Via MQTT',
                'Created At', 'Updated At'
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

    @app.after_request
    def add_security_headers(response):
        """Add basic security headers"""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response