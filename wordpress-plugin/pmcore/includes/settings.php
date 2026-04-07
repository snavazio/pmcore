<?php
defined( 'ABSPATH' ) || exit;

// ── Register setting ──────────────────────────────────────────────────────────

function pmcore_register_settings() {
    register_setting(
        'pmcore',
        'pmcore_api_url',
        [
            'type'              => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default'           => PMCORE_API_DEFAULT,
        ]
    );
}
add_action( 'admin_init', 'pmcore_register_settings' );

// ── Admin menu ────────────────────────────────────────────────────────────────

function pmcore_add_settings_page() {
    add_options_page(
        'PMCore API Settings',
        'PMCore API',
        'manage_options',
        'pmcore-settings',
        'pmcore_render_settings_page'
    );
}
add_action( 'admin_menu', 'pmcore_add_settings_page' );

// ── Settings page HTML ────────────────────────────────────────────────────────

function pmcore_render_settings_page() {
    if ( ! current_user_can( 'manage_options' ) ) {
        return;
    }
    $api_url = get_option( 'pmcore_api_url', PMCORE_API_DEFAULT );
    ?>
    <div class="wrap">
        <h1><?php esc_html_e( 'PMCore API Settings', 'pmcore' ); ?></h1>

        <form method="post" action="options.php">
            <?php settings_fields( 'pmcore' ); ?>

            <table class="form-table" role="presentation">
                <tr>
                    <th scope="row">
                        <label for="pmcore_api_url">API URL</label>
                    </th>
                    <td>
                        <input
                            type="url"
                            id="pmcore_api_url"
                            name="pmcore_api_url"
                            value="<?php echo esc_attr( $api_url ); ?>"
                            class="regular-text"
                            placeholder="http://100.110.246.22:8765"
                        />
                        <p class="description">
                            The base URL of your PMCore API server (no trailing slash).<br>
                            Default: <code><?php echo esc_html( PMCORE_API_DEFAULT ); ?></code>
                        </p>
                    </td>
                </tr>
                <tr>
                    <th scope="row">Connection test</th>
                    <td>
                        <button type="button" class="button" id="pmcore-test-btn">
                            Test Connection
                        </button>
                        <span id="pmcore-test-result" style="margin-left:10px;"></span>
                        <script>
                        document.getElementById('pmcore-test-btn').addEventListener('click', function() {
                            var url = document.getElementById('pmcore_api_url').value.replace(/\/$/, '');
                            var result = document.getElementById('pmcore-test-result');
                            result.textContent = 'Testing...';
                            fetch(url + '/health')
                                .then(function(r) { return r.json(); })
                                .then(function(d) {
                                    result.style.color = 'green';
                                    result.textContent = 'Connected — ' + (d.gpu ? d.gpu.name : 'no GPU info') + ' | ' + d.version;
                                })
                                .catch(function(e) {
                                    result.style.color = 'red';
                                    result.textContent = 'Failed: ' + e.message;
                                });
                        });
                        </script>
                    </td>
                </tr>
            </table>

            <?php submit_button(); ?>
        </form>

        <hr>
        <h2>Usage</h2>
        <p>Add <code>[pmcore]</code> to any page or post to embed the PMCore planning UI.</p>
        <p>Optional attribute: <code>[pmcore placeholder="Describe your IT project..."]</code></p>
    </div>
    <?php
}
