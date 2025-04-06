import cv2
import numpy as np
from PIL import Image
from rembg import remove
import io
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D


async def processImg(input_path: str):
   

    def process_image_pipeline(
        input_path: str,
        
        # remove_background_ai parameters
        bg_removed_path: str = "steps/background_removed.png",
        output_path: str = "steps/contour.png",
        # process_image parameters
        process_cell_size: int = 1,
        
        # createPointsArray parameters
        points_cellWidth: int = 1,
        upperLeftEdge: list = None,
        bottomRightEdge: list = None
    ):
        
        bg_removed_path = remove_background_ai(input_path, bg_removed_path)
        
        contour_output = get_single_pixel_contour(bg_removed_path, output_path)

        matrix = process_image(contour_output, process_cell_size)
            
        points = createPointsArray(
            matrix,
            points_cellWidth,
            upperLeftEdge,
            bottomRightEdge
        )

        visualization3D(points)
        
        return points


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

        

    def get_single_pixel_contour(image_path, output_path):
        # Load the image in grayscale
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

        # Check image orientation
        height, width = image.shape
        if height > width:  # If the image is vertical, rotate it 90 degrees
            image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)

        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(image, (3, 3), 0)
        
        # Use Canny edge detection
        edges = cv2.Canny(blurred, 190, 191)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        # Create a blank white image
        contour_image = np.ones_like(image) * 255
        
        # Draw contours with a single pixel width
        cv2.drawContours(contour_image, contours, -1, (0,), 1)

        cv2.imwrite(output_path, contour_image)

        return output_path

    # Step 2: Process image into matrix with cell_size=1
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

    def createPointsArray(matrix, cellWidth, upperLeftEdge, bottomRightEdge):
        #cellWidth, x, y, z -> mm
        #a,e,r -> degree
        
        height = len(matrix)
        width = len(matrix[0]) if height > 0 else 0

        total_width = bottomRightEdge[0] - upperLeftEdge[0]
        total_height = bottomRightEdge[1] - upperLeftEdge[1]
        
        step_x = total_width / width
        step_y = total_height / height

        visited = set()
        sequences = []

        def get_neighbors(i, j):
            directions = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
            return [(i+di, j+dj) for di, dj in directions if 0 <= i+di < height and 0 <= j+dj < width]

        def trace_sequence(i, j):
            stack = [(i, j)]
            sequence = []
            while stack:
                ci, cj = stack.pop()
                if (ci, cj) in visited:
                    continue
                visited.add((ci, cj))
                x = round(upperLeftEdge[0] + cj * step_x + cellWidth/2)
                y = round(upperLeftEdge[1] + ci * step_y + cellWidth/2)
                z = round(upperLeftEdge[2])
                a = round(upperLeftEdge[3])
                e = round(upperLeftEdge[4])
                r = round(upperLeftEdge[5])
                
                sequence.append([x, y, z, a, e, r])
                for ni, nj in get_neighbors(ci, cj):
                    if matrix[ni][nj] == 1 and (ni, nj) not in visited:
                        stack.append((ni, nj))
            return sequence

        for i in range(height):
            for j in range(width):
                if matrix[i][j] == 1 and (i, j) not in visited:
                    sequences.append(trace_sequence(i, j))

        path = []
        for seq in sequences:
            if path:
                path.append([path[-1][0], path[-1][1], path[-1][2]+10, -3,88,-2])  # Lift arm before moving
                path.append([seq[0][0], seq[0][1], seq[0][2]+10, -3,88,-2])  # Move to new sequence start
            path.extend(seq)

        result = []
        for item in path:
            if item not in result:
                result.append(item)
        return result

    def visualization3D(matrix):
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D

        matrix = [item for item in matrix if item[2] != -109]
        xs = [point[0] for point in matrix]
        ys = [point[1] for point in matrix]
        zs = [point[2] for point in matrix]

        fig = plt.figure(figsize=(10, 10))
        ax = fig.add_subplot(111, projection='3d')

        point_size = 10
        ax.scatter(xs, ys, zs, c='b', marker='o', s=point_size, edgecolors='none', antialiased=True)

        ax.set_xlabel('X (mm)')
        ax.set_ylabel('Y (mm)')
        ax.set_zlabel('Z (mm)')

        ax.view_init(elev=-90, azim=-90)

        ax.set_zticks([])
        ax.zaxis.set_ticklabels([])
        ax.zaxis.line.set_color((0, 0, 0, 0))

        plt.savefig("steps/sketch.png", bbox_inches='tight', dpi=600)
        plt.close(fig)


    points = process_image_pipeline(
        input_path,
        bg_removed_path="steps/background_removed.png",
        output_path="steps/contour.png",
        process_cell_size=1,
        points_cellWidth=1,
        upperLeftEdge=[170, 65, -119, -3,88,-2],
        bottomRightEdge=[601, 403, -119, -3,88,-2]
    )
   
    return points

