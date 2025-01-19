from flask import Flask, render_template, request, jsonify
import openrouteservice
import folium
from openrouteservice.optimization import Vehicle, Job
import numpy as np
# venv\Scripts\activate 
app = Flask(__name__)

# OpenRouteService API Key
api_key = '5b3ce3597851110001cf624840be9462232a466e91cbf0c6286cbd13'
client = openrouteservice.Client(key=api_key)

def optimize_route(coordinates):
    coordinates_ors = [(coord[1], coord[0]) for coord in coordinates]
    
    jobs = [Job(id=i, location=coord) for i, coord in enumerate(coordinates_ors)]
    vehicles = [Vehicle(id=1, profile='driving-car', start=coordinates_ors[0], end=coordinates_ors[0])]
    
    try:
        optimized_route = client.optimization(
            jobs=jobs,
            vehicles=vehicles
        )
    except openrouteservice.exceptions.ApiError as e:
        print("Error during initial optimization:", str(e))
        if 'Unfound route' in str(e):
            matrix = client.distance_matrix(
                locations=coordinates_ors,
                profile='driving-car',
                metrics=['distance'],
            )
            
            distance_matrix = np.array(matrix['distances'])
            np.fill_diagonal(distance_matrix, np.inf)
            nearest_points = np.argmin(distance_matrix, axis=1)
            
            new_jobs = []
            for i, job in enumerate(jobs):
                nearest_point = coordinates_ors[nearest_points[i]]
                new_jobs.append(Job(id=i, location=nearest_point))
            
            optimized_route = client.optimization(
                jobs=new_jobs,
                vehicles=vehicles
            )
    
    return optimized_route

def calculate_total_distance(optimized_coordinates):
    total_distance = 0
    for i in range(len(optimized_coordinates) - 1):
        try:
            route = client.directions(
                coordinates=[optimized_coordinates[i], optimized_coordinates[i + 1]],
                profile="driving-car",
                format="geojson",
            )
            distance = route["features"][0]["properties"]["segments"][0]["distance"]
            total_distance += distance
        except openrouteservice.exceptions.ApiError as e:
            print(f"API error while calculating distance: {e}")
        except Exception as e:
            print(f"An error occurred while calculating distance: {e}")
    return total_distance / 1000  # Convert to kilometers

def create_map(optimized_route, original_coordinates):
    optimized_coordinates = []
    optimized_order = []
    for step in optimized_route['routes'][0]['steps']:
        if 'job' in step:
            optimized_coordinates.append(step['location'])
            optimized_order.append(step['job'])

    total_distance = calculate_total_distance(optimized_coordinates)

    map_center = [original_coordinates[0][0], original_coordinates[0][1]]
    route_map = folium.Map(location=map_center, zoom_start=13)

    for i, coord in enumerate(optimized_coordinates):
        folium.Marker(
            location=[coord[1], coord[0]],
            icon=folium.DivIcon(html=f'<div style="font-size: 12pt; color : black">{optimized_order[i] + 1}</div>'),
        ).add_to(route_map)

    folium.PolyLine(
        locations=[(coord[1], coord[0]) for coord in optimized_coordinates],
        color="blue",
        weight=2.5,
        opacity=1
    ).add_to(route_map)

    return route_map._repr_html_(), optimized_order, total_distance

def calculate_total_distance_for_sequence(sequence):
    total_distance = 0
    for i in range(len(sequence) - 1):
        try:
            route = client.directions(
                coordinates=[sequence[i], sequence[i + 1]],
                profile="driving-car",
                format="geojson",
            )
            distance = route["features"][0]["properties"]["segments"][0]["distance"]
            total_distance += distance
        except openrouteservice.exceptions.ApiError as e:
            print(f"API error while calculating distance: {e}")
        except Exception as e:
            print(f"An error occurred while calculating distance: {e}")
    return total_distance / 1000

def create_map_for_sequence(sequence, map_center, title):
    route_map = folium.Map(location=map_center, zoom_start=13)

    for i, coord in enumerate(sequence):
        folium.Marker(
            location=[coord[1], coord[0]],
            icon=folium.DivIcon(html=f'<div style="font-size: 12pt; color : black">{i + 1}</div>'),
        ).add_to(route_map)

    folium.PolyLine(
        locations=[(coord[1], coord[0]) for coord in sequence],
        color="blue" if title == "Optimized Route" else "red",
        weight=2.5,
        opacity=1
    ).add_to(route_map)

    return route_map._repr_html_()

def calculate_emissions_reduction(unrouted_distance, optimized_distance, fuel_consumption_rate, fuel_emission_factor, vehicle_efficiency):
    fuel_unrouted = unrouted_distance / vehicle_efficiency * fuel_consumption_rate
    fuel_optimized = optimized_distance / vehicle_efficiency * fuel_consumption_rate
    emissions_unrouted = fuel_unrouted * fuel_emission_factor
    emissions_optimized = fuel_optimized * fuel_emission_factor
    return emissions_unrouted - emissions_optimized

def translate_emissions_reduction(emissions_reduction_kg):
    CO2_PER_TREE_YEAR = 21
    CO2_PER_KM_CAR = 0.05
    CO2_PER_KWH_ENERGY = 0.23
    CO2_PER_APPLE = 0.3
    CO2_PER_WASTE_KG = 0.5
    CO2_PER_SOLAR_MINUTES = 0.13
    CO2_PER_PUBLIC_TRANSPORT_KM = 0.03

    return {
        "Trees Saved": emissions_reduction_kg / CO2_PER_TREE_YEAR,
        "Distance by Car (km)": emissions_reduction_kg / CO2_PER_KM_CAR,
        "Energy Saved (kWh)": emissions_reduction_kg / CO2_PER_KWH_ENERGY,
        "Food Offset (Apples)": emissions_reduction_kg / CO2_PER_APPLE,
        "Waste Offset (kg)": emissions_reduction_kg / CO2_PER_WASTE_KG,
        "Renewable Energy Contribution (minutes)": emissions_reduction_kg / CO2_PER_SOLAR_MINUTES,
        "Public Transport Equivalent (km)": emissions_reduction_kg / CO2_PER_PUBLIC_TRANSPORT_KM
    }

@app.route('/optimize', methods=['POST'])
def optimize():
    try:
        data = request.json
        coordinates = data.get('coordinates', [])

        if not coordinates:
            return jsonify({'error': 'No coordinates provided'}), 400

        # Original order (unrouted)
        unrouted_coordinates = [(coord[1], coord[0]) for coord in coordinates]
        unrouted_distance = calculate_total_distance_for_sequence(unrouted_coordinates)
        unrouted_map = create_map_for_sequence(unrouted_coordinates, coordinates[0], "Unrouted Route")

        # Optimized route
        optimized_route = optimize_route(coordinates)
        optimized_coordinates = [step['location'] for step in optimized_route['routes'][0]['steps'] if 'job' in step]
        optimized_distance = calculate_total_distance_for_sequence(optimized_coordinates)
        optimized_map = create_map_for_sequence(optimized_coordinates, coordinates[0], "Optimized Route")

        # Calculate emissions reduction
        fuel_consumption_rate = 0.08
        fuel_emission_factor = 2.3
        vehicle_efficiency = 15
        emissions_reduction = calculate_emissions_reduction(
            unrouted_distance, optimized_distance, fuel_consumption_rate, fuel_emission_factor, vehicle_efficiency
        )

        # Translate emissions reduction
        translated_emissions = translate_emissions_reduction(emissions_reduction)

        return jsonify({
            'success': True,
            'unrouted_map': unrouted_map,
            'optimized_map': optimized_map,
            'unrouted_distance': unrouted_distance,
            'optimized_distance': optimized_distance,
            'emissions_reduction': emissions_reduction,
            'translated_emissions': translated_emissions
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Routes
@app.route('/dashboard', methods=['GET'])
def dashboard():
    return render_template('dashboard.html')

@app.route('/package_optimisation', methods=['GET'])
def package_optimisation():
    return render_template('package_optimisation.html')

@app.route('/route_optimisation', methods=['GET'])
def route_optimisation():
    return render_template('route_optimisation.html')

@app.route('/warehouse_optimisation', methods=['GET'])
def warehouse_optimisation():
    return render_template('warehouse_optimisation.html')

@app.route('/', methods=['GET'])
def index():
    return render_template('dashboard.html')

if __name__ == '__main__':
    app.run()