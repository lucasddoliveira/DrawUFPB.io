import cv2
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import networkx as nx
from sklearn.cluster import DBSCAN
from rembg import remove
import io

async def processImg(input_path: str):


    def clean_alpha_edges(image: Image.Image, threshold=10):
        # Convert to RGBA if not already
        image = image.convert("RGBA")
        data = np.array(image)

        # Extract alpha channel
        r, g, b, a = data.T

        # Replace partially transparent pixels with full transparency
        mask = a < threshold
        data[..., :-1][mask.T] = (255, 255, 255)  # Optional: make transparent pixels white
        data[..., -1][mask.T] = 0  # Fully transparent

        return Image.fromarray(data)

    def erode_alpha(image: Image.Image, pixels=1):
        image = image.convert("RGBA")
        data = np.array(image)
        alpha = data[..., 3]
        kernel = np.ones((3, 3), np.uint8)
        eroded_alpha = cv2.erode(alpha, kernel, iterations=pixels)
        data[..., 3] = eroded_alpha
        return Image.fromarray(data)

    def remove_background_ai(input_path: str, output_path: str = "steps/background_removed.png"):
        with open(input_path, "rb") as inp_file:
            img = Image.open(io.BytesIO(inp_file.read()))
            img_no_bg = remove(img)
            img_no_bg = clean_alpha_edges(img_no_bg)
            img_no_bg = erode_alpha(img_no_bg, pixels=1)
            img_no_bg.save(output_path, "PNG")
        return output_path
    

    def extract_contours(image_path, threshold1=120, threshold2=191, blur_size=3):
        """Extract contours from an image using Canny edge detection, with flood fill to avoid double borders."""

        # Load the image in grayscale
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        
        # Check image orientation
        height, width = image.shape
        if height > width:  # If the image is vertical, rotate it 90 degrees
            image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)

        # Flood fill from top-left corner to unify background
        flood_filled = image.copy()
        h, w = flood_filled.shape[:2]
        mask = np.zeros((h + 2, w + 2), np.uint8)  # Mask needs to be 2 pixels larger than the image
        cv2.floodFill(flood_filled, mask, seedPoint=(0, 0), newVal=255)  # Flood with white
        cv2.floodFill(flood_filled, mask, seedPoint=(0, 0), newVal=0)    # Then flood with black

        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(flood_filled, (blur_size, blur_size), 0)

        # Detect edges using Canny
        edges = cv2.Canny(blurred, threshold1, threshold2)

        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        # Create a blank white image
        contour_image = np.ones_like(image) * 255

        # Draw contours with a single pixel width
        cv2.drawContours(contour_image, contours, -1, (0,), 1)

        # Save result
        cv2.imwrite("steps/contour.png", contour_image)

        return image, edges, contours, contour_image

    def simplify_contours(contours, epsilon_factor=0.0001):
        """Simplify contours using Douglas-Peucker algorithm."""
        simplified_contours = []
        
        for contour in contours:
            # Calculate epsilon based on the perimeter of the contour
            epsilon = epsilon_factor * cv2.arcLength(contour, True)
            simplified = cv2.approxPolyDP(contour, epsilon, True)
            simplified_contours.append(simplified)
        
        return simplified_contours

    def filter_contours(contours, min_length=10):
        """Filter out small contours."""
        return [cnt for cnt in contours if len(cnt) >= min_length]

    def process_image(input_path, cell_size=1):
        img = Image.open(input_path).convert("L")
        width, height = img.size
        # Overlay grid (optional, but uses cell_size=1)
        overlay = img.convert("RGB")
        
        overlay.save("steps/contour.png")
        img_array = np.array(img)
        grid_rows = height // cell_size
        grid_cols = width // cell_size
        matrix = np.zeros((grid_rows, grid_cols), dtype=int)
        for i in range(grid_rows):
            for j in range(grid_cols):
                # For cell_size=1, each cell is a single pixel
                matrix[i, j] = 1 if img_array[i, j] < 128 else 0
        return matrix.tolist()

    def createPointsArray(matrix, cellWidth, upperLeftEdge, bottomRightEdge, z_up=10, z_down=0, distance_threshold=3, epsilon=0.25):
        """Enhanced createPointsArray with robotic arm movement logic, distance constraint and line approximation."""
        import numpy as np
        height = len(matrix)
        width = len(matrix[0]) if height > 0 else 0

        total_width = bottomRightEdge[0] - upperLeftEdge[0]
        total_height = bottomRightEdge[1] - upperLeftEdge[1]
        
        step_x = total_width / width
        step_y = total_height / height
        
        # Prepare to collect points
        points = []
        visited = set()
        
        def get_neighbors(i, j):
            # All 8 possible directions (up, down, left, right, and diagonals)
            directions = [
                (-1, 0), (1, 0),  # up, down
                (0, -1), (0, 1),  # left, right
                (-1, -1), (-1, 1),  # top-left, top-right
                (1, -1), (1, 1)     # bottom-left, bottom-right
            ]
            return [(i+di, j+dj) for di, dj in directions if 0 <= i+di < height and 0 <= j+dj < width]
        
        def trace_sequence(i, j):
            # Use BFS instead of DFS to ensure connected components stay together
            queue = [(i, j)]
            sequence = []
            local_visited = set([(i, j)])  # Track visited cells for this sequence
            
            while queue:
                ci, cj = queue.pop(0)  # BFS uses queue (FIFO)
                if (ci, cj) in visited:
                    continue
                visited.add((ci, cj))
                
                # Convert to physical coordinates
                x = round(upperLeftEdge[0] + cj * step_x + cellWidth/2)
                y = round(upperLeftEdge[1] + ci * step_y + cellWidth/2)
                z = round(upperLeftEdge[2])
                a = round(upperLeftEdge[3])
                e = round(upperLeftEdge[4])
                r = round(upperLeftEdge[5])
                
                sequence.append([x, y, z, a, e, r])
                
                for ni, nj in get_neighbors(ci, cj):
                    if matrix[ni][nj] == 1 and (ni, nj) not in visited and (ni, nj) not in local_visited:
                        queue.append((ni, nj))
                        local_visited.add((ni, nj))  # Mark as to-be-visited
            
            return sequence
        
        # Douglas-Peucker line simplification algorithm
        def simplify_line(points, epsilon):
            if len(points) <= 2:
                return points
            
            # Find the point with the maximum distance from line between start and end
            max_dist = 0
            index = 0
            start, end = points[0], points[-1]
            
            # Line equation: ax + by + c = 0
            if end[0] == start[0]:  # Vertical line
                for i in range(1, len(points) - 1):
                    dist = abs(points[i][0] - start[0])
                    if dist > max_dist:
                        max_dist = dist
                        index = i
            else:
                a = (end[1] - start[1]) / (end[0] - start[0])
                b = -1
                c = start[1] - a * start[0]
                
                for i in range(1, len(points) - 1):
                    dist = abs(a * points[i][0] + b * points[i][1] + c) / np.sqrt(a**2 + b**2)
                    if dist > max_dist:
                        max_dist = dist
                        index = i
            
            # If max distance is greater than epsilon, recursively simplify
            if max_dist > epsilon:
                # Recursive call
                first_segment = simplify_line(points[:index + 1], epsilon)
                second_segment = simplify_line(points[index:], epsilon)
                
                # Build the result (avoid duplicating the connection point)
                return first_segment[:-1] + second_segment
            else:
                # All points are within epsilon distance from the line
                return [points[0], points[-1]]
        
        # Collect all sequences
        sequences = []
        for i in range(height):
            for j in range(width):
                if matrix[i][j] == 1 and (i, j) not in visited:
                    sequences.append(trace_sequence(i, j))
        
        # Apply line simplification to each sequence
        simplified_sequences = []
        for seq in sequences:
            points_only = [p[:2] for p in seq]  # Extract x,y coordinates
            simplified_points = simplify_line(points_only, epsilon)
            
            # Reconstruct full 6D points with original z,a,e,r values
            simplified_seq = []
            for x, y in simplified_points:
                # Find the closest original point to get its z,a,e,r values
                min_dist = float('inf')
                best_match = None
                for orig_point in seq:
                    dist = (orig_point[0] - x)**2 + (orig_point[1] - y)**2
                    if dist < min_dist:
                        min_dist = dist
                        best_match = orig_point
                
                simplified_seq.append([x, y, best_match[2], best_match[3], best_match[4], best_match[5]])
            
            simplified_sequences.append(simplified_seq)
        
        # Optimize sequence order to minimize travel distance
        optimized_sequences = []
        current_pos = None
        remaining_sequences = list(range(len(simplified_sequences)))
        
        while remaining_sequences:
            if current_pos is None:
                # Start with the first sequence
                next_seq = 0
                optimized_sequences.append(simplified_sequences[next_seq])
                current_pos = simplified_sequences[next_seq][-1][:2]  # Just need x, y coords
                remaining_sequences.remove(next_seq)
            else:
                # Find the closest sequence
                min_dist = float('inf')
                next_seq = None
                
                for i in remaining_sequences:
                    start_dist = np.sqrt((current_pos[0] - simplified_sequences[i][0][0])**2 + 
                                        (current_pos[1] - simplified_sequences[i][0][1])**2)
                    
                    if start_dist < min_dist:
                        min_dist = start_dist
                        next_seq = i
                
                optimized_sequences.append(simplified_sequences[next_seq])
                current_pos = simplified_sequences[next_seq][-1][:2]
                remaining_sequences.remove(next_seq)
        
        # Create the final path with pen up/down movements
        path = []
        for seq in optimized_sequences:
            if path:
                # Get the last point's coordinates
                last_x, last_y, last_z, last_a, last_e, last_r = path[-1]
                new_x, new_y = seq[0][0], seq[0][1]
                
                # Calculate distance to the new sequence
                dist = np.sqrt((new_x - last_x)**2 + (new_y - last_y)**2)
                
                # If distance is large, add pen up/down movements
                if dist > distance_threshold:
                    # Lift the pen at current position
                    path.append([last_x, last_y, last_z + z_up, last_a, last_e, last_r])
                    # Move to new sequence start (pen up)
                    path.append([new_x, new_y, seq[0][2] + z_up, seq[0][3], seq[0][4], seq[0][5]])
                    # Lower the pen at new position
                    path.append([new_x, new_y, seq[0][2], seq[0][3], seq[0][4], seq[0][5]])
                else:
                    # Direct movement to the next sequence (pen down)
                    path.append([new_x, new_y, seq[0][2], seq[0][3], seq[0][4], seq[0][5]])
            
            # Add the current sequence
            path.extend(seq)
        
        # Make sure we end with pen up
        if path:
            last_point = path[-1]
            path.append([last_point[0], last_point[1], last_point[2] + z_up, 
                        last_point[3], last_point[4], last_point[5]])
        
        # Remove duplicate consecutive points
        result = []
        for item in path:
            if not result or item != result[-1]:
                result.append(item)
        
        return result

    def visualization3D(points):
        """Visualize the 3D path with color-coded pen up/down movements."""
        if not points:
            return
            
        # Extract x, y, z coordinates
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        zs = [abs(point[2]) for point in points]
        
        # Determine pen state for each point (up/down)
        # Assuming points with z > upperLeftEdge[2] are pen up
        base_z = points[0][2]
        pen_states = ['up' if point[2] < base_z else 'down' for point in points]
        
        # Create colormap: blue for pen down, red for pen up
        colors = ['b' if state == 'down' else 'r' for state in pen_states]
        
        # Create the 3D visualization
        fig = plt.figure(figsize=(12, 10))
        ax = fig.add_subplot(111, projection='3d')
        
        # Plot the path
        for i in range(1, len(points)):
            x_line = [xs[i-1], xs[i]]
            y_line = [ys[i-1], ys[i]]
            z_line = [zs[i-1], zs[i]]
            ax.plot(x_line, y_line, z_line, color=colors[i], linewidth=1)
        
        # Plot points
        ax.scatter(xs, ys, zs, c=colors, marker='o', s=20, edgecolors='none')
        
        # Add start and end markers
        ax.scatter([xs[0]], [ys[0]], [zs[0]], c='g', marker='o', s=100, label='Start')
        ax.scatter([xs[-1]], [ys[-1]], [zs[-1]], c='y', marker='o', s=100, label='End')
        
        # Set labels and title
        ax.set_xlabel('X (mm)')
        ax.set_ylabel('Y (mm)')
        ax.set_zlabel('Z (mm)')
        ax.set_title('Robotic Arm Path')
        
        # Add legend
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], marker='o', color='w', markerfacecolor='b', markersize=10, label='Pen Down'),
            Line2D([0], [0], marker='o', color='w', markerfacecolor='r', markersize=10, label='Pen Up'),
            Line2D([0], [0], marker='o', color='w', markerfacecolor='g', markersize=10, label='Start'),
            Line2D([0], [0], marker='o', color='w', markerfacecolor='y', markersize=10, label='End')
        ]
        ax.legend(handles=legend_elements, loc='upper right')
        
        # Save the figure
        plt.savefig("steps/3d_path.png", bbox_inches='tight', dpi=300)
        
        # Create a top-down view for the 2D sketch
        fig2 = plt.figure(figsize=(10, 10))
        ax2 = fig2.add_subplot(111)
        
        # Plot only pen-down segments for the sketch
        for i in range(1, len(points)):
            if pen_states[i] == 'down' and pen_states[i-1] == 'down':
                ax2.plot([xs[i-1], xs[i]], [ys[i-1], ys[i]], 'b-', linewidth=1.0)
        
        ax2.set_xlabel('X (mm)')
        ax2.set_ylabel('Y (mm)')
        ax2.set_title('Drawing Path (Top View)')
        ax2.set_aspect('equal')
        ax2.invert_yaxis()  # <-- Corrige a orientação
        
        plt.savefig("steps/sketch.png", bbox_inches='tight', dpi=600)
        plt.close(fig)
        plt.close(fig2)

    def process_image_pipeline(
        input_path,
        output_path="steps/contour.png",
        process_cell_size=1,
        points_cellWidth=1,
        upperLeftEdge=None,
        bottomRightEdge=None,
        z_up=-10
    ):
        # Extract and process contours
        bg_removed_path = remove_background_ai(input_path)

        image, edges, contours, contour_image = extract_contours(bg_removed_path)
        
        # Simplify contours to reduce complexity
        simplified_contours = simplify_contours(contours)
        
        # Filter out small contours
        filtered_contours = filter_contours(simplified_contours)
        
        # Convert to 2D matrix
        cv2.imwrite(output_path, contour_image)
        matrix = process_image(output_path, process_cell_size)
        
        # If boundaries not provided, use defaults based on image dimensions
        if upperLeftEdge is None:
            upperLeftEdge = [170, 65, -118, -3, 88, -2]
        if bottomRightEdge is None:
            height, width = contour_image.shape
            bottomRightEdge = [601, 403, -118, -3, 88, -2]
        
        # Create the optimized points array with robotic arm movements
        points = createPointsArray(
            matrix,
            points_cellWidth,
            upperLeftEdge,
            bottomRightEdge,
            z_up=z_up
        )
        
        # Visualize the results
        visualization3D(points)
        
        # Save the robot movement commands to a file
        save_robot_commands(points, "steps/robot_commands.txt")
        
        return points

    def save_robot_commands(commands, filename="steps/robot_commands.txt"):
        """Save the robot commands to a file."""
        with open(filename, 'w') as f:
            for cmd in commands:
                f.write(f"{cmd[0]:.2f},{cmd[1]:.2f},{cmd[2]:.2f},{cmd[3]:.2f},{cmd[4]:.2f},{cmd[5]:.2f}\n")
        print(f"Saved {len(commands)} robot commands to {filename}")

    # Set up default parameters for edge detection
    points = process_image_pipeline(
        input_path,
        output_path="steps/contour.png",
        process_cell_size=1,
        points_cellWidth=1,
        upperLeftEdge=[170, 65, -118, -3, 88, -2],
        bottomRightEdge=[601, 403, -118, -3, 88, -2],
        z_up=-10
    )
    
    return points