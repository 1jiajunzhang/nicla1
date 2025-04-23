import struct
from vpython import *
from pyquaternion import Quaternion
from bleak import BleakClient
import asyncio
import threading
import math
import numpy as np
import csv
import os
import keyboard  
from vpython import scene, wtext

# Eliminated forearm lag and connectivity issues.  
# Fixed reconnection mechanism. Added all exercises (so far)
# Applied Textures, no bumpmap
# Added rotation to limbs with visual joints.
# Corrected some exercises.
# Added CSV output for each exercise.
# Added interpolation.
# Added exercise demonstration (incomplete)
# Found sweet spot for interpolation
# Added exercise compliance function
# Improved exercise compliance function
# Completed exercise demonstration 
# Adding force sensor (incomplete)
# added in scene text

# VPython Scene Setup for user
scene = canvas(title="You", width=800, height=600, background=color.black)
# Create a wtext element below the main scene
status_display = wtext(text="Initializing...\n")

# Set the camera for the desired view
scene.camera.pos = vector(5, 5, 2)  # Camera placed in 3D space at (5, 5, 2)
scene.camera.axis = vector(-5, -5, -2)  # Point the camera towards the origin, focusing on (0,0,0)
scene.camera.up = vector(0, 0, 1)  # Set the "up" direction as the Z-axis, so Z points up

# Axis indicators (X, Y, Z)
axis_length = 3  # Length of the axis arrows
x_axis = arrow(canvas=scene, pos=vector(0, 0, 0), axis=vector(axis_length, 0, 0), color=color.red, shaftwidth=0.05)
y_axis = arrow(canvas=scene, pos=vector(0, 0, 0), axis=vector(0, axis_length, 0), color=color.green, shaftwidth=0.05)
z_axis = arrow(canvas=scene, pos=vector(0, 0, 0), axis=vector(0, 0, axis_length), color=color.blue, shaftwidth=0.05)

# Open CSV file once and create an iterator
csv_file = "Reach_Back.csv"
csv_clean_file = "Clean_Rotation_in_Abduction.csv"
csv_iterator = iter(csv.reader(open(csv_clean_file, newline='')))

# Function to create the humerus bone model
def create_humerus(position, canvas):
    # Create a low-poly humerus bone model at the given position
    shaft = cylinder(canvas = canvas, pos=position, axis=vector(1, 0, 0), radius=0.15, color=color.white)
    head = box(canvas = canvas, pos=position, size=vector(0.3, 0.3, 0.3), color=color.white)  # Shoulder joint (fixed pivot)
    bone = compound([shaft, head], origin=position, texture = textures.wood_old)
    bone.scene = canvas
    return bone

# Function to create the humerus bone model
def create_radius(position, canvas):
    # Create a low-poly humerus bone model at the given position
    shaft = cylinder(canvas = canvas, pos=position, axis=vector(1.0, 0, 0), radius=0.125, color = color.white)
    epiphysis = box(canvas = canvas, pos=vector(2,0,0), size=vector(0.25, 0.25, 0.25), color=color.white)
    bone = compound([shaft, epiphysis], origin=position, texture = textures.wood_old)
    bone.scene = canvas
    return bone

# Create the first humerus at the origin
humerus_bone = create_humerus(vector(0, 0, 0), scene)

humerus_quat = Quaternion()

# Create the radius next to the humerus (shifted along the y-axis)
radius_bone = create_radius(vector(1, 0, 0), scene)

radius_quat = Quaternion()

relevant_quat = Quaternion()

record_flag = False

current_force = 0.00

# VPython Scene Setup for dummy
dummy_scene = canvas(title="Demonstration", width=800, height=600, background=color.white)

# Set the camera for the desired dummy view
dummy_scene.camera.pos = vector(5, 5, 2)  # Camera placed in 3D space at (5, 5, 5)
dummy_scene.camera.axis = vector(-5, -5, -2)  # Point the camera towards the origin, focusing on (0,0,0)
dummy_scene.camera.up = vector(0, 0, 1)  # Set the "up" direction as the Z-axis, so Z points up

# Dummy axis indicators (X, Y, Z)
dummy_x_axis = arrow(canvas=dummy_scene, pos=vector(0, 0, 0), axis=vector(axis_length, 0, 0), color=color.red, shaftwidth=0.05)
dummy_y_axis = arrow(canvas=dummy_scene, pos=vector(0, 0, 0), axis=vector(0, axis_length, 0), color=color.green, shaftwidth=0.05)
dummy_z_axis = arrow(canvas=dummy_scene, pos=vector(0, 0, 0), axis=vector(0, 0, axis_length), color=color.blue, shaftwidth=0.05)

# Create the first dummy humerus at the origin
dummy_humerus_bone = create_humerus(vector(0, 0, 0), dummy_scene)

dummy_humerus_quat = Quaternion()

# Create the dummy radius next to the dummy humerus (shifted along the y-axis)
dummy_radius_bone = create_radius(vector(1, 0, 0), dummy_scene)

dummy_radius_quat = Quaternion()

async def apply_quaternion_rotation(obj, q_new, radius_bone, humerus_bone, num_interpolation_steps = 12):
    global humerus_quat, radius_quat

    # Determine the previous quaternion
    q_prev = humerus_quat if obj == humerus_bone else radius_quat
    
    # Generate interpolated quaternions if the jump is too large
    for i in range(1, num_interpolation_steps + 1):
        t = i / num_interpolation_steps  # Interpolation factor
        q_interp = Quaternion.slerp(q_prev, q_new, t)

        # Convert quaternion to rotation matrix
        R = q_interp.rotation_matrix

        # Extract the rotated Y-axis (default bone axis in VPython)
        new_axis = vector(R[0][1], R[1][1], R[2][1])  # Rotated local y-axis
        
        # Ensure rotation is applied correctly without incremental drift
        obj.axis = new_axis  # Align object with new axis
        obj.up = vector(R[0][2], R[1][2], R[2][2])  # Set the 'up' direction for correct rotation

        # Update bone positions correctly
        if obj == humerus_bone:
            radius_bone.pos = new_axis
            humerus_quat = q_interp
        else:
            radius_bone.pos = humerus_bone.axis
            radius_quat = q_interp

async def apply_quaternion_rotation_dummy(dummy_radius_bone, dummy_humerus_bone):
    global dummy_humerus_quat, dummy_radius_quat, csv_iterator
    try:
        try:    
            # Read the next row
            row = next(csv_iterator)
        except StopIteration:
            # Restart from the beginning when reaching the end
            csv_iterator = iter(csv.reader(open(csv_clean_file, newline='')))
            row = next(csv_iterator)  # Read first row again after reset

        # Convert the first 4 values to a quaternion for the humerus
        dummy_humerus_quat = Quaternion(float(row[0]), float(row[1]), float(row[2]), float(row[3]))

        # Convert the next 4 values to a quaternion for the radius
        dummy_radius_quat = Quaternion(float(row[4]), float(row[5]), float(row[6]), float(row[7]))

        # Convert quaternions to rotation matrices
        R_humerus = dummy_humerus_quat.rotation_matrix
        R_radius = dummy_radius_quat.rotation_matrix

        # Extract the rotated Y-axis (default bone axis in VPython)
        humerus_axis = vector(R_humerus[0][1], R_humerus[1][1], R_humerus[2][1])
        radius_axis = vector(R_radius[0][1], R_radius[1][1], R_radius[2][1])

        # Apply rotations
        dummy_humerus_bone.axis = humerus_axis
        dummy_humerus_bone.up = vector(R_humerus[0][2], R_humerus[1][2], R_humerus[2][2])

        dummy_radius_bone.axis = radius_axis
        dummy_radius_bone.up = vector(R_radius[0][2], R_radius[1][2], R_radius[2][2])

        # Ensure radius position updates relative to humerus
        dummy_radius_bone.pos = dummy_humerus_bone.axis
    except:
        #print("Dummy Print Error")
        pass


async def notification_handler(sender, data, bone):
    try:
        qW, qX, qY, qZ = struct.unpack('<ffff', data[:16])
        q = Quaternion(qW, qX, qY, qZ)
        await apply_quaternion_rotation(bone, q, radius_bone, humerus_bone)
    except Exception as e:
        print(f"Error in notification handler: {e}")

async def notification_handler_force(sender, data):
    global current_force
    try:
        current_force, throw,throw2,throw3 = struct.unpack('<ffff', data[:16])
    except Exception as e:
        print(f"Error in notification handler: {e}")


async def connect_to_device(address, uuid, bone):
    while True:  # Keep retrying if disconnected
        try:
            print(f"Attempting to connect to device {address}...")
            async with BleakClient(address) as client:
                if await client.is_connected():
                    print(f"Connected to {address}")

                # Start notifications
                await client.start_notify(uuid, lambda sender, data: asyncio.create_task(notification_handler(sender, data, bone)))

                # Keep connection alive
                while await client.is_connected():
                    await asyncio.sleep(0.1)  # Check connection status periodically

                print(f"Disconnected from {address}, retrying...")

        except Exception as e:
            print(f"Error with device {address}: {e}")

        # Wait before retrying to prevent excessive reconnect attempts
        await asyncio.sleep(0.6)

async def connect_to_device_force(address, uuid, current_force):
    while True:  # Keep retrying if disconnected
        try:
            print(f"Attempting to connect to device {address}...")
            async with BleakClient(address) as client:
                if await client.is_connected():
                    print(f"Connected to {address}")

                # Start notifications
                await client.start_notify(uuid, lambda sender, data: asyncio.create_task(notification_handler_force(sender, data)))

                # Keep connection alive
                while await client.is_connected():
                    await asyncio.sleep(0.1)  # Check connection status periodically

                print(f"Disconnected from {address}, retrying...")

        except Exception as e:
            print(f"Error with device {address}: {e}")

        # Wait before retrying to prevent excessive reconnect attempts
        await asyncio.sleep(0.6)


# Calculation Section #
async def calculate_abduction_angle(humerus_quat):
    """Calculate the angle between the humerus and the vertical Z-axis for abduction."""
    # Extract the rotated humerus axis using the rotation matrix from the quaternion
    R = humerus_quat.rotation_matrix
    humerus_axis = vector(R[0][1], R[1][1], R[2][1])  # Extract Y-axis as the bone axis

    # Define the vertical Z-axis
    z_axis = vector(0, 0, 1)
    
    # Calculate the angle between the two vectors
    angle = math.acos(max(-1.0, min(1.0, humerus_axis.dot(z_axis))))  # Clamping for safety
    return math.degrees(angle)


async def calculate_elbow_angle(humerus_quat, radius_quat):
    """Calculate the angle between the humerus and radius bones."""
    # Extract the humerus and radius axes using the rotation matrices from the quaternions
    R_humerus = humerus_quat.rotation_matrix
    R_radius = radius_quat.rotation_matrix
    
    humerus_axis = vector(R_humerus[0][1], R_humerus[1][1], R_humerus[2][1])  # Extract Y-axis as the humerus axis
    radius_axis = vector(R_radius[0][1], R_radius[1][1], R_radius[2][1])  # Extract Y-axis as the radius axis
    
    # Calculate the angle between the two axes
    angle = math.acos(max(-1.0, min(1.0, humerus_axis.dot(radius_axis))))
    return math.degrees(angle)


async def calculate_rotation_abduction(humerus_quat, radius_quat):
    """Calculate the angle between the radius and a vector perpendicular to the humerus."""
    # Extract rotation matrices
    R_humerus = humerus_quat.rotation_matrix
    R_radius = radius_quat.rotation_matrix
    
    # Humerus Y-axis
    humerus_axis = vector(R_humerus[0][1], R_humerus[1][1], R_humerus[2][1])
    
    # Find a vector perpendicular to the humerus axis (cross with a fixed reference, e.g., Z-axis)
    reference_vector = vector(0, 0, 1)  # Assuming Z-axis as a reference
    perpendicular_vector = humerus_axis.cross(reference_vector)
    
    # Normalize perpendicular vector
    perpendicular_vector = perpendicular_vector.norm()
    
    # Extract radius Y-axis
    radius_axis = vector(R_radius[0][1], R_radius[1][1], R_radius[2][1])
    
    # Compute the angle between the perpendicular vector and radius axis
    angle = math.acos(max(-1.0, min(1.0, perpendicular_vector.dot(radius_axis))))
    
    #angle_deg = math.degrees(angle)

    return math.degrees(angle)


async def calculate_angle(exercise_number, humerus_quat, radius_quat):
    """Asynchronous function to determine which shoulder angle to calculate based on the exercise number."""
    filename = None
    data_row = None
    headers = None
    global record_flag

    if exercise_number == 1:  # Shoulder Abduction
        shoulder_abduction_angle = await calculate_abduction_angle(humerus_quat)
        filename = "Shoulder_Abduction.csv"
        headers = ["Humerus_w", "Humerus_x", "Humerus_y", "Humerus_z", 
                   "Radius_w", "Radius_x", "Radius_y", "Radius_z", 
                   "Angle"]
        data_row = [
                    round(humerus_quat.w, 3), round(humerus_quat.x, 3), round(humerus_quat.y, 3), round(humerus_quat.z, 3), 
                    round(radius_quat.w, 3), round(radius_quat.x, 3), round(radius_quat.y, 3), round(radius_quat.z, 3),
                    round(shoulder_abduction_angle, 1)]
        print(f"Abduction angle: {round(shoulder_abduction_angle, 1)}", end="\r", flush=True)

    elif exercise_number == 2:  # Reach Back
        reachback_elbow_angle = await calculate_elbow_angle(humerus_quat, radius_quat)
        reachback_abduction_angle = await calculate_abduction_angle(humerus_quat)
        filename = "Reach_Back.csv"
        headers = ["Humerus_w", "Humerus_x", "Humerus_y", "Humerus_z", 
                   "Radius_w", "Radius_x", "Radius_y", "Radius_z", 
                   "Elbow_Angle", "Abduction_Angle"]
        data_row = [
                    round(humerus_quat.w, 3), round(humerus_quat.x, 3), round(humerus_quat.y, 3), round(humerus_quat.z, 3),
                    round(radius_quat.w, 3), round(radius_quat.x, 3), round(radius_quat.y, 3), round(radius_quat.z, 3),
                    round(reachback_elbow_angle, 1), round(reachback_abduction_angle, 1)
            ]
        print(f"Elbow angle: {round(reachback_elbow_angle, 1)} Elevation angle: {round(reachback_abduction_angle, 1)}", end="\r", flush=True)

    elif exercise_number == 3:  # Rotation in Abduction
        rotation_in_abduction_angle = await calculate_rotation_abduction(humerus_quat, radius_quat)
        filename = "Rotation_in_Abduction.csv"
        headers = ["Humerus_w", "Humerus_x", "Humerus_y", "Humerus_z", 
                   "Radius_w", "Radius_x", "Radius_y", "Radius_z", 
                   "Rotation_Angle"]
        data_row = [
                    round(humerus_quat.w, 3), round(humerus_quat.x, 3), round(humerus_quat.y, 3), round(humerus_quat.z, 3),
                    round(radius_quat.w, 3), round(radius_quat.x, 3), round(radius_quat.y, 3), round(radius_quat.z, 3),
                    round(rotation_in_abduction_angle, 1)]
        print(f"Rotation angle: {round(rotation_in_abduction_angle, 1)}", end="\r", flush=True)

    elif exercise_number == 4:  # Rotation in Neutral
        neutral_rotation_angle = await calculate_rotation_abduction(humerus_quat, radius_quat)
        filename = "Rotation_in_Neutral.csv"
        headers = ["Humerus_w", "Humerus_x", "Humerus_y", "Humerus_z", 
                   "Radius_w", "Radius_x", "Radius_y", "Radius_z", 
                   "Rotation_Angle"]
        data_row = [
                    round(humerus_quat.w, 3), round(humerus_quat.x, 3), round(humerus_quat.y, 3), round(humerus_quat.z, 3),
                    round(radius_quat.w, 3), round(radius_quat.x, 3), round(radius_quat.y, 3), round(radius_quat.z, 3),
                    neutral_rotation_angle]
 
    if record_flag:
        if filename:
            file_exists = os.path.isfile(filename)

            #Open file in append mode, write header only if it does not exist
            with open(filename, "a", newline="") as file:
                writer = csv.writer(file)

                if not file_exists:
                    writer.writerow(headers)  # Write headers only once

                writer.writerow(data_row)  # Append data

async def run_on_spacebar():
    global record_flag
    while True:
        if keyboard.is_pressed('space'):
            record_flag = not record_flag
        await asyncio.sleep(0.01)  # Delay to prevent CPU hogging

async def exercise_with_compliance(humerus_quat, radius_quat, current_force):
    expected_abduction_angle = 90
    expected_elbow_angle = 90

    filename = "Rotation_in_Abduction.csv"
    data_row = None
    headers = None
    global record_flag
    
    # Calculate the angles using the functions above
    calculated_abduction_angle = await calculate_abduction_angle(humerus_quat)
    calculated_elbow_angle = await calculate_elbow_angle(humerus_quat, radius_quat)
    rotation_in_abduction_angle = await calculate_rotation_abduction(humerus_quat, radius_quat)
            
    # Compare calculated angles to expected angles within a small tolerance (e.g., 5 degrees)
    tolerance = 10  # Tolerance in degrees

    abduction_correct = abs(calculated_abduction_angle - expected_abduction_angle) <= tolerance
    elbow_correct = abs(calculated_elbow_angle - expected_elbow_angle) <= tolerance
    headers = ["Humerus_w", "Humerus_x", "Humerus_y", "Humerus_z", 
                "Radius_w", "Radius_x", "Radius_y", "Radius_z", 
                "Rotation_Angle"]
    data_row = [
                round(humerus_quat.w, 3), round(humerus_quat.x, 3), round(humerus_quat.y, 3), round(humerus_quat.z, 3),
                round(radius_quat.w, 3), round(radius_quat.x, 3), round(radius_quat.y, 3), round(radius_quat.z, 3),
                round(rotation_in_abduction_angle, 1)]

    # Print the result based on which angles are correct or incorrect
    print(f"Humerus Correct? {abduction_correct} Radius Correct? {elbow_correct} | Force:{current_force:.2f}lbs, Abduction: {calculated_abduction_angle:.2f}°, Elbow: {calculated_elbow_angle:.2f}°, Rotation: {rotation_in_abduction_angle:.2f}°", end="\r", flush=True)
    status_display.text = f"""
                            Humerus OK? {abduction_correct} | Elbow OK? {elbow_correct}
                            Force: {current_force:.2f} lbs
                            Abduction: {calculated_abduction_angle:.1f}°
                            Elbow: {calculated_elbow_angle:.1f}°
                            Rotation: {rotation_in_abduction_angle:.1f}°
                            """


    if record_flag:
        if filename:
            file_exists = os.path.isfile(filename)

            #Open file in append mode, write header only if it does not exist
            with open(filename, "a", newline="") as file:
                writer = csv.writer(file)

                if not file_exists:
                    writer.writerow(headers)  # Write headers only once

                writer.writerow(data_row)  # Append data
   
# Main function to handle both devices simultaneously
async def main():
    address1 = "DD:43:D5:61:71:13"  # Humerus
    address2 = "6F:8F:9D:FD:18:7C"  # Radius
    address3 = "5E:F3:F7:62:E3:36"  # Force
    uuid1 = "2A90"  # Humerus
    uuid2 = "2A91"  # Radius
    uuid3 = "2A92"  # Force
    exercise_number = 2  

    # Run connections in parallel
    asyncio.create_task(connect_to_device(address1, uuid1, humerus_bone))
    asyncio.create_task(connect_to_device(address2, uuid2, radius_bone))
    asyncio.create_task(connect_to_device_force(address3, uuid3, current_force))
    # Check for record
    asyncio.create_task(run_on_spacebar())
    while True:
        # Call the dummy function to apply quaternion rotation
        await apply_quaternion_rotation_dummy(dummy_radius_bone, dummy_humerus_bone)
        #rate(500)
        await exercise_with_compliance(humerus_quat, radius_quat, current_force)
        #await calculate_angle(exercise_number, humerus_quat, radius_quat)
        await asyncio.sleep(0.05)

# Run the asyncio loop
asyncio.run(main())
