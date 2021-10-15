import hunger as h

# Helpers ----------------------------------------------------------------------------------

import json
import plotly.express as px

district_color_map = {
    "1": "#FEFB32",
    "2": "#8B429E",
    "3": "#DD8210",
    "4": "#B3DF8A",
    "5": "#1C7638"}

with open("assets/" + h.scale + "/geo.json", encoding='utf8') as file:
    geojson = json.load(file)

def getMapFor(state = None, title=None):
    if state == None:
        state = h.Solver.getDummyDataFrame()

    fig = px.choropleth(state,
                    geojson = geojson,
                    locations='code', hover_data=['region','metric','district'],
                    color='district',
                    scope="usa",
    )
    fig.update_layout(showlegend=False, margin={"r":0,"l":0,"b":0}, title=title)

    return fig

def getChartFor(state = None):
    if state == None:
        state = h.Solver.getDummyDataFrame()

    fig = px.pie(
        state,
        values="metric", names="district",
        hover_name="district", hover_data=["metric"],
        color="district",
    )

    return fig

# App implementation ----------------------------------------------------------------------------------

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State
from flask import request

# initialize the solver
solvers = {}

# make the app GUI
app = dash.Dash(__name__)
app.layout = html.Div([
    dcc.Store(id='solution'),
    html.Div(id='ticker', children=False, style={'display': 'none'}),

    # Interface
    html.Div([
        # Buttons
        html.Button("Solve", id='solve'),
        html.Button("Pause/Resume", id='pause', n_clicks=0),
        html.Button("Step", id='step'),
        html.Button("Reset", id='reset'),

        # The dropdown to pick metrics
        dcc.Dropdown(
            id='metric-drop',
            options=[{'label': metric + (" (broken)" if metric in h.broken else ""), 'value': metric} for metric in h.metrics],
            value=h.allowed[0],
            clearable=False,
            style={
                'width': '40%'
            }
        ),
        # The dropdown to pick the number of districts
        dcc.Dropdown(
            id='count-drop',
            options=[{'label': i, 'value': i} for i in range(2,11)],
            #options=[{'label': 50, 'value': 50}],
            value=5,
            clearable=False,
            style={
                'width': '40%'
            }
        )
    ], style={'display': 'flex'}),

    # Plots
    html.Div([
        html.Div([
            dcc.Graph(id='map', figure=getMapFor(), style={'height': '100%'})
        ], className="eight columns", style={'height': '100%', 'vertical-align': 'top'}),

        html.Div([
            dcc.Graph(id='pie-chart', figure=getChartFor())
        ], className="four columns"),
    ], className="row", style={'height': '100%'})
], style={'height': '90vh'})

# Callback to draw the charts
@app.callback([Output('map',        'figure'),
               Output('pie-chart',  'figure'),
               Output('ticker',     'children')],
              [Input('solution',    'data')])
def drawCharts(solution):
    return getMapFor(solution), getChartFor(solution), True

# Monolithic callback to do map updates and respond to button presses
@app.callback([Output('solution',   'data'),
               Output('solve',      'disabled'),
               Output('pause',      'disabled'),
               Output('step',       'disabled')],
              [Input('ticker',      'children'),
               Input('solve',       'n_clicks'),
               Input('pause',       'n_clicks'),
               Input('step',        'n_clicks'),
               Input('reset',       'n_clicks')],
              [State('metric-drop', 'value'),
               State('count-drop',  'value')])
def solveStepwise(tick, solveClicks, pauseClicks, stepClicks, resetClicks, metric, count):
    # Initialize the data
    ctx = dash.callback_context.triggered[0]['prop_id'].split('.')[0]
    paused = pauseClicks % 2 == 0
    broken = metric in h.broken

    # Initialize the unique solver for this user
    ip = request.remote_addr
    if ip not in solvers:
        solvers[ip] = h.Solver(metric, count)
    s = solvers[ip]

    # Ignore overflowed messages when we're solved or if one of the broken options was picked
    if ctx not in ['reset','pause'] and (s.isSolved() or broken):
        print("Ignoring overflow message ({})".format(ctx))
        raise dash.exceptions.PreventUpdate()

    # If an incrementing feature happened, take a step
    elif ctx == 'step':
        print("Step ({})".format(ctx))
        s.doStep()

    elif ctx == 'ticker':
        if not paused:
            s.doStep()
        else:
            # Cancel out of the callback if we shouldn't be ticking!
            raise dash.exceptions.PreventUpdate()

    # If the user pressed the reset button, reset the solver with the provided metric
    elif ctx == 'reset':
        print("Reset the map with metric {}".format(metric))
        s.reset(metric, count)

    # If the user pressed the solve button, insta-solve!
    elif ctx == 'solve':
        print("Rapid-solving")
        s.solve()

    # If the user pressed the pause button, just log it
    elif ctx == 'pause':
        if paused:      print("Paused")
        else:           print("Resumed")

    shouldBlockStep = broken or s.isSolved()

    return s.getCurrentDataFrame(), shouldBlockStep, paused and shouldBlockStep, not paused or shouldBlockStep