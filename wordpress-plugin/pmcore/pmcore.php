<?php
/**
 * Plugin Name:  PMCore
 * Plugin URI:   https://github.com/snavazio/pmcore
 * Description:  AI-powered project management planning via the PMCore pipeline (PMPlanner + PMReasoner + PMCommunicator + PMMath). Use [pmcore] shortcode on any page.
 * Version:      1.0.0
 * Author:       snavazio
 * License:      MIT
 */

defined( 'ABSPATH' ) || exit;

define( 'PMCORE_VERSION',    '1.0.0' );
define( 'PMCORE_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'PMCORE_PLUGIN_URL', plugin_dir_url( __FILE__ ) );
define( 'PMCORE_API_DEFAULT', 'http://100.110.246.22:8765' );

// ── Settings ──────────────────────────────────────────────────────────────────

require_once PMCORE_PLUGIN_DIR . 'includes/settings.php';

// ── Assets ────────────────────────────────────────────────────────────────────

function pmcore_enqueue_assets() {
    wp_enqueue_style(
        'pmcore-styles',
        PMCORE_PLUGIN_URL . 'assets/pmcore.css',
        [],
        PMCORE_VERSION
    );

    wp_enqueue_script(
        'pmcore-script',
        PMCORE_PLUGIN_URL . 'assets/pmcore.js',
        [],
        PMCORE_VERSION,
        true   // footer
    );

    // Pass API URL to JS
    wp_localize_script( 'pmcore-script', 'PMCoreConfig', [
        'apiUrl' => esc_url_raw( get_option( 'pmcore_api_url', PMCORE_API_DEFAULT ) ),
    ] );
}
add_action( 'wp_enqueue_scripts', 'pmcore_enqueue_assets' );

// ── Shortcode [pmcore] ────────────────────────────────────────────────────────

function pmcore_shortcode( $atts ) {
    $atts = shortcode_atts( [
        'placeholder' => 'Describe your project, budget, team size, and timeline...',
    ], $atts, 'pmcore' );

    ob_start();
    ?>
    <div class="pmcore-wrap" id="pmcore-app">

        <form class="pmcore-form" id="pmcore-form" novalidate>

            <div class="pmcore-field">
                <label for="pmcore-request" class="pmcore-label">
                    Project Description
                </label>
                <textarea
                    id="pmcore-request"
                    name="request"
                    class="pmcore-textarea"
                    rows="4"
                    placeholder="<?php echo esc_attr( $atts['placeholder'] ); ?>"
                    required
                ></textarea>
            </div>

            <div class="pmcore-field">
                <label for="pmcore-comm-type" class="pmcore-label">
                    Communication Type
                </label>
                <select id="pmcore-comm-type" name="comm_type" class="pmcore-select">
                    <option value="Write a professional project kickoff summary for stakeholders.">Kickoff Email</option>
                    <option value="Write a weekly status report for the project steering committee.">Status Report</option>
                    <option value="Write an executive summary of the project plan and risks.">Executive Summary</option>
                    <option value="Write a risk escalation memo for senior leadership.">Risk Escalation</option>
                </select>
            </div>

            <div class="pmcore-submit-row">
                <button type="submit" class="pmcore-btn wp-element-button" id="pmcore-submit">
                    <span class="pmcore-btn-text">Generate Plan</span>
                    <span class="pmcore-spinner" aria-hidden="true" style="display:none;"></span>
                </button>
                <span class="pmcore-status" id="pmcore-status" aria-live="polite"></span>
            </div>

        </form>

        <div class="pmcore-results" id="pmcore-results" style="display:none;" aria-live="polite">

            <div class="pmcore-results-grid">

                <div class="pmcore-section" id="pmcore-planner">
                    <h3 class="pmcore-section-title">Project Plan</h3>
                    <div class="pmcore-section-body" id="pmcore-planner-body"></div>
                </div>

                <div class="pmcore-section" id="pmcore-reasoner">
                    <h3 class="pmcore-section-title">Risk Analysis</h3>
                    <div class="pmcore-section-body" id="pmcore-reasoner-body"></div>
                </div>

            </div>

            <div class="pmcore-section pmcore-section--wide" id="pmcore-communicator">
                <h3 class="pmcore-section-title">
                    Communication
                    <button class="pmcore-copy-btn" id="pmcore-copy-btn" title="Copy to clipboard" type="button">
                        Copy
                    </button>
                </h3>
                <div class="pmcore-section-body pmcore-prose" id="pmcore-comm-body"></div>
            </div>

            <div class="pmcore-section pmcore-section--audit" id="pmcore-math-audit">
                <h3 class="pmcore-section-title">Math Audit</h3>
                <div class="pmcore-section-body" id="pmcore-audit-body"></div>
            </div>

        </div>

        <div class="pmcore-error" id="pmcore-error" style="display:none;" role="alert"></div>

    </div>
    <?php
    return ob_get_clean();
}
add_shortcode( 'pmcore', 'pmcore_shortcode' );
