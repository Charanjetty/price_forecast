import os
import io
try:
    import joblib
    JOBLIB_AVAILABLE = True
except Exception:
    joblib = None
    JOBLIB_AVAILABLE = False
import pandas as pd
import numpy as np
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# ROOT points to the project root (one level above the predictor app)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# Model and scaler are expected at project root: <project>/price_model.pkl
MODEL_PATH = os.path.join(ROOT, 'price_model.pkl')
SCALER_PATH = os.path.join(ROOT, 'scaler.pkl')


def index(request):
    # Server-rendered dashboard: load dataset (or demo), compute simple forecast and metrics
    csv_path = os.path.join(ROOT, 'price_data.csv')
    app_csv_path = os.path.join(os.path.dirname(__file__), 'price_data.csv')
    
    # Try loading from either location
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, parse_dates=['date'])
    elif os.path.exists(app_csv_path):
        df = pd.read_csv(app_csv_path, parse_dates=['date'])
    else:
        rng = pd.date_range(start='2015-01-01', periods=120, freq='MS')
        trend = np.linspace(1000, 2000, len(rng))
        seasonal = 80 * np.sin(2 * np.pi * (rng.month - 1) / 12)
        df = pd.DataFrame({'date': rng, 'avg_monthly_price': trend + seasonal})
    
    # Rename avg_monthly_price to price for consistency
    if 'avg_monthly_price' in df.columns:
        df = df.rename(columns={'avg_monthly_price': 'price'})

    df = df.sort_values('date').drop_duplicates('date').reset_index(drop=True)
    if df['price'].isnull().any():
        df['price'] = df['price'].interpolate(method='time').ffill().bfill()

    # prepare history rows (last 48 points)
    hist_rows = []
    start = max(0, len(df) - 48)
    for i in range(start, len(df)):
        hist_rows.append({
            'date': df['date'].iloc[i].strftime('%Y-%m-%d'),
            'actual': float(df['price'].iloc[i])
        })

    # forecast horizon configurable via GET param (horizon), default 12
    try:
        horizon = int(request.GET.get('horizon', 12))
    except Exception:
        horizon = 12
    horizon = max(1, min(36, horizon))

    # simple linear trend extrapolation for demo forecast (use recent points for slope)
    n_trend = min(24, len(df))
    if n_trend >= 2:
        x = np.arange(len(df))[-n_trend:]
        y = df['price'].values[-n_trend:]
        try:
            coeff = np.polyfit(x, y, 1)
            slope = float(coeff[0])
        except Exception:
            slope = 0.0
    else:
        slope = 0.0

    last_price = float(df['price'].iloc[-1])
    future_dates = pd.date_range(start=df['date'].iloc[-1] + pd.DateOffset(months=1), periods=horizon, freq='MS')
    fc_list = []
    prev = last_price
    for i, d in enumerate(future_dates):
        val = float(last_price + slope * (i + 1))
        pct = ((val - prev) / prev) * 100 if prev != 0 else 0.0
        fc_list.append({'date': d.strftime('%Y-%m-%d'), 'forecast': val, 'change_pct': pct})
        prev = val

    avg_forecast = float(np.mean([r['forecast'] for r in fc_list])) if fc_list else None

    metrics = {
        'mae': None,
        'rmse': None,
        'trend_pct': float(((avg_forecast - last_price) / last_price) * 100) if last_price != 0 else 0.0,
        'accuracy': None,
        'confidence': None,
    }

    context = {
        'history': hist_rows,
        'forecast': fc_list,
        'current_price': last_price,
        'avg_forecast': avg_forecast,
        'metrics': metrics,
    }
    return render(request, 'predictor/index.html', context)


@csrf_exempt
def predict(request):
    # Try to load model if available; otherwise run in demo mode
    model = None
    scaler = None
    model_loaded = False
    if JOBLIB_AVAILABLE and os.path.exists(MODEL_PATH):
        try:
            model = joblib.load(MODEL_PATH)
            model_loaded = True
        except Exception:
            model_loaded = False

    if os.path.exists(SCALER_PATH) and JOBLIB_AVAILABLE:
        try:
            scaler = joblib.load(SCALER_PATH)
        except Exception:
            scaler = None

    # load dataset: uploaded file or price_data.csv in project root
    if request.method == 'POST' and request.FILES.get('file'):
        csvfile = request.FILES['file']
        df = pd.read_csv(csvfile, parse_dates=['date'])
    else:
        csv_path = os.path.join(ROOT, 'price_data.csv')
        if not os.path.exists(csv_path):
            # return demo data if none provided
            rng = pd.date_range(start='2015-01-01', periods=120, freq='MS')
            trend = np.linspace(1000, 2000, len(rng))
            seasonal = 80 * np.sin(2 * np.pi * (rng.month - 1) / 12)
            df = pd.DataFrame({'date': rng, 'price': trend + seasonal})
        else:
            df = pd.read_csv(csv_path, parse_dates=['date'])

    df = df.sort_values('date').drop_duplicates('date').reset_index(drop=True)
    # basic cleaning
    if df['price'].isnull().any():
        df['price'] = df['price'].interpolate(method='time').ffill().bfill()

    # feature engineering - should match how you trained model
    df['month'] = df['date'].dt.month
    df['t'] = np.arange(len(df))
    df['month_sin'] = np.sin(2 * np.pi * (df['month'] - 1) / 12)
    df['month_cos'] = np.cos(2 * np.pi * (df['month'] - 1) / 12)

    FEATURES = ['t', 'month_sin', 'month_cos']

    # Build X for historical predictions if model expects scaled features
    X_hist = df[FEATURES].values
    if scaler is not None:
        try:
            X_hist = scaler.transform(X_hist)
        except Exception:
            pass

    # predicted historical (optional) - use model if available, else fall back to actuals
    if model is not None:
        try:
            hist_preds = model.predict(X_hist)
        except Exception as e:
            return JsonResponse({'error': 'Model predict failed on historical data: ' + str(e)}, status=500)
    else:
        # demo behavior: predicted == actuals (no model)
        hist_preds = df['price'].values.copy()

    # evaluation metrics on recent period (last 12 months where both actual & predicted exist)
    # compute MAE/RMSE on last min(12, len(df)) points
    n_eval = min(12, len(df))
    y_true = df['price'].values[-n_eval:]
    y_pred = hist_preds[-n_eval:]
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))

    # Forecast next 12 months - construct future features consistent with training
    last_t = int(df['t'].iloc[-1])
    future_dates = pd.date_range(start=df['date'].iloc[-1] + pd.DateOffset(months=1), periods=12, freq='MS')
    future = pd.DataFrame({'date': future_dates})
    future['month'] = future['date'].dt.month
    future['t'] = np.arange(last_t + 1, last_t + 1 + len(future))
    future['month_sin'] = np.sin(2 * np.pi * (future['month'] - 1) / 12)
    future['month_cos'] = np.cos(2 * np.pi * (future['month'] - 1) / 12)
    X_future = future[['t', 'month_sin', 'month_cos']].values
    if scaler is not None:
        X_future = scaler.transform(X_future)

    if model is not None:
        try:
            future_preds = model.predict(X_future)
        except Exception as e:
            return JsonResponse({'error': 'Model predict failed on future data: ' + str(e)}, status=500)
    else:
        # Demo forecasting: simple linear trend extrapolation using last 12 months
        if len(df) >= 2:
            n_trend = min(12, len(df))
            x = df['t'].values[-n_trend:]
            y = df['price'].values[-n_trend:]
            # linear fit
            try:
                coeff = np.polyfit(x, y, 1)
                slope = float(coeff[0])
            except Exception:
                slope = 0.0
        else:
            slope = 0.0
        last_price = float(df['price'].iloc[-1])
        future_preds = [last_price + slope * (i + 1) for i in range(len(future_dates))]

    # compute monthly change %
    prev = df['price'].iloc[-1]
    fc_list = []
    for i, d in enumerate(future_dates):
        val = float(future_preds[i])
        pct = ((val - prev) / prev) * 100 if prev != 0 else 0.0
        fc_list.append({'date': d.strftime('%Y-%m-%d'), 'forecast': val, 'change_pct': pct})
        prev = val

    avg_forecast = float(np.mean(future_preds))

    # prepare history array (limit to last 48 points to keep payload small)
    hist_rows = []
    start = max(0, len(df) - 48)
    for i in range(start, len(df)):
        hist_rows.append({
            'date': df['date'].iloc[i].strftime('%Y-%m-%d'),
            'actual': float(df['price'].iloc[i]),
            'predicted': float(hist_preds[i])
        })

    metrics = {
        'mae': mae,
        'rmse': rmse,
        'trend_pct': float(((avg_forecast - df['price'].iloc[-1]) / df['price'].iloc[-1]) * 100) if df['price'].iloc[-1] != 0 else 0.0,
        # optional fields for UI
        'accuracy': None,
        'confidence': 95
    }

    result = {
        'current_price': float(df['price'].iloc[-1]),
        'metrics': metrics,
        'history': hist_rows,
        'forecast': fc_list,
        'avg_forecast': avg_forecast
    }

    return JsonResponse(result, safe=True)
