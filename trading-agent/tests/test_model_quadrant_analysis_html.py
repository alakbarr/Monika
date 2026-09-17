# ==============================================================================
# File: tests/test_model_quadrant_analysis_html.py
# ==============================================================================

import json
import re
from pathlib import Path
import pytest

root_dir = Path(__file__).resolve().parent.parent.parent
html_path = root_dir / "trading-agent" / "benchmark" / "results" / "model_quadrant_analysis.html"
if not html_path.exists():
    html_path = root_dir / "model_quadrant_analysis.html"


@pytest.fixture
def html_content():
    assert html_path.exists(), f"{html_path} does not exist"
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def raw_models(html_content):
    m = re.search(r"const rawModels = (\[.*?\]);", html_content)
    assert m is not None, "rawModels JSON array not found in HTML"
    return json.loads(m.group(1))


def test_html_file_exists_and_size():
    assert html_path.exists()
    assert html_path.stat().st_size > 50000


def test_data_integrity_72_models(raw_models):
    assert len(raw_models) == 72
    ids = [m["id"] for m in raw_models]
    assert ids == list(range(1, 73)), "Model IDs must be 1 to 72"

    for m in raw_models:
        assert "provider" in m
        assert "model" in m
        assert "thinking" in m
        assert isinstance(m["score"], (int, float))
        assert isinstance(m["cost"], (int, float))
        assert m["score"] > 0
        assert m["cost"] >= 0.0


def test_tooltip_enterable_and_confine(html_content):
    # Tooltip must be enterable and confined so CTA button can be clicked
    assert "enterable: true" in html_content
    assert "confine: true" in html_content
    assert "setThresholdsFromModelId" in html_content


def test_log_scale_handling_for_zero_cost(html_content, raw_models):
    # Models with cost = 0.0 exist (ID 62 and 70)
    zero_cost_models = [m for m in raw_models if m["cost"] == 0.0]
    assert len(zero_cost_models) >= 2, "Expected models with 0.0 cost"

    # HTML script must define log floor handling for plotting
    assert "logFloor" in html_content
    assert "Math.max(m.cost, logFloor)" in html_content
    assert "Math.max(costThreshold, logFloor)" in html_content


def test_table_quadrant_sorting_and_indicators(html_content):
    # Header must have data-sort="quadrant"
    assert 'data-sort="quadrant"' in html_content
    # quadrantRank and thinkingRank must exist in script
    assert "quadrantRank" in html_content
    assert "thinkingRank" in html_content
    # Table header must include .arr spans and aria-sort
    assert 'class="arr"' in html_content
    assert "aria-sort" in html_content


def test_slider_bounds_harmonization(html_content):
    # Score min 20, max 60
    assert 'id="numScore" type="number" min="20.0" max="60.0"' in html_content
    assert 'id="rangeScore" type="range" min="20.0" max="60.0"' in html_content
    # Cost min 0, max 2
    assert 'id="numCost" type="number" min="0.000" max="2.000"' in html_content
    assert 'id="rangeCost" type="range" min="0.000" max="2.000"' in html_content
    # Step labels and aria
    assert 'aria-label="Kurangi skor 1.0"' in html_content
    assert 'aria-label="Kurangi biaya $0.05"' in html_content


def test_kpi_filter_synchronization(html_content):
    # updateKPIs must use getFilteredModels()
    assert "function getFilteredModels()" in html_content
    assert "const activeModels = getFilteredModels();" in html_content


def test_csv_export_uses_blob_and_utf8_bom(html_content):
    # Export must use Blob with UTF-8 BOM (\uFEFF)
    assert r"\uFEFF" in html_content or "\uFEFF" in html_content
    assert "new Blob(" in html_content
    assert "URL.createObjectURL(" in html_content


def test_chart_click_mode_bounds_and_escape(html_content):
    # containPixel prevents click triggers outside the chart grid
    assert "containPixel({ gridIndex: 0 }" in html_content
    # Escape key disables click mode
    assert "Escape" in html_content
    assert "disableClickMode" in html_content


def test_accessibility_attributes(html_content):
    # Tabs have role="tab" and aria-selected
    assert 'role="tab"' in html_content
    assert "aria-selected" in html_content
    # Preset buttons have aria-pressed
    assert "aria-pressed" in html_content
    # Filter pills have aria-pressed
    assert 'class="tag-pill provider-pill" aria-pressed="true"' in html_content
    assert 'class="tag-pill thinking-pill" aria-pressed="true"' in html_content
    # Sortable table headers have tabindex="0"
    assert 'tabindex="0"' in html_content
    assert "triggerSort" in html_content


def test_x_axis_bounds_and_mark_area(html_content):
    # X-axis max must be 2.0 to prevent clipping thresholds up to $2.000
    assert "min: currentScale === 'log' ? logFloor : 0, max: 2.0," in html_content
    assert "const maxX = currentScale === 'log' ? 2.05 : 2.05;" in html_content


def test_legend_excludes_quadrants(html_content):
    # ECharts legend must explicitly list real providers to avoid showing dummy 'Quadrants'
    assert "legend: { data: providers.map(displayName)" in html_content


def test_chart_scatter_click_to_table_interaction(html_content):
    # Clicking scatter point on chart focuses and highlights model in table
    assert "myChart.on('click'" in html_content
    assert "window.focusChartModel(m.id, null, false)" in html_content


def test_focus_chart_model_tab_switch_and_scroll(html_content):
    # focusChartModel must automatically switch activeTableTab if model is in different quadrant
    assert "activeTableTab = modelQuad" in html_content
    assert "row.scrollIntoView" in html_content
    # focusChartModel must support both model ID and modelName + thinking
    assert "typeof modelIdOrName === 'string'" in html_content


def test_step_attributes_validity(html_content):
    # Step attributes must allow exact decimal representations of median & mean
    assert 'step="0.01"' in html_content
    assert 'step="0.001"' in html_content


def test_legend_and_scatter_color_synchronization(html_content):
    # Root option must supply provider palette colors
    assert "color: providerPalette" in html_content
    # Series must assign provider color to itemStyle and set z=5 above overlay
    assert "itemStyle: { color: pColor }" in html_content
    assert "z: 5" in html_content


def test_mark_series_z_index_under_scatter(html_content):
    # markSeries and markArea must have z: 1 so quadrant overlay renders underneath scatter points
    assert "name: 'Quadrants', type: 'scatter', data: [], silent: true, z: 1" in html_content
    assert "silent: true,\n      z: 1,\n      data:" in html_content or "z: 1" in html_content


def test_legend_select_changed_sync(html_content):
    # myChart must listen to legendselectchanged to sync filter pills, KPIs, and table
    assert "myChart.on('legendselectchanged'" in html_content
    assert "selectedProviders.has(prov)" in html_content


def test_quadrant_legend_swatch_styling_and_label(html_content):
    # Legend row must visually represent quadrant areas with distinctive swatches
    assert "sw--sweet" in html_content
    assert "sw--premium" in html_content
    assert "sw--budget" in html_content
    assert "sw--lagging" in html_content
    assert "Zona Latar:" in html_content


def test_zero_cost_display_and_search_by_id(html_content):
    # Cost for 0.00 models must display $0.00 instead of <$0.01
    assert "m.cost === 0 ? '$0.00'" in html_content
    # Table search must support searching by model ID
    assert "String(m.id) === query" in html_content
    assert "String(m.id) === query.replace('#', '')" in html_content


