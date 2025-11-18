"""
Category Manager Module for Avirta

This module handles the management of categories, including creating,
updating, and organizing categories for questions.
"""

class CategoryManager:
    """
    A class to manage Avirta question categories.

    Attributes:
        categories (dict): Dictionary of categories with their properties
        category_hierarchy (dict): Hierarchical structure of categories
        default_category (str): Default category ID for uncategorized questions
    """

    def __init__(self):
        """
        Initialize a new category manager.
        """
        self.categories = {}
        self.category_hierarchy = {}
        self.default_category = "general"

        # Initialize with a default general category
        self.add_category("general", "General Knowledge")

    def add_category(self, category_id, name, parent_id=None, description=None, icon=None):
        """
        Add a new category.

        Args:
            category_id (str): Unique identifier for the category
            name (str): Display name of the category
            parent_id (str, optional): ID of parent category. Defaults to None.
            description (str, optional): Description of the category. Defaults to None.
            icon (str, optional): Icon or image for the category. Defaults to None.

        Returns:
            bool: True if category was added successfully, False otherwise
        """
        if category_id in self.categories:
            return False

        # Create the category
        self.categories[category_id] = {
            'name': name,
            'description': description or f"Questions about {name}",
            'icon': icon,
            'parent_id': parent_id,
            'question_count': 0,
            'active': True
        }

        # Update hierarchy
        if parent_id:
            if parent_id not in self.categories:
                # If parent doesn't exist, create as top-level
                parent_id = None
                self.categories[category_id]['parent_id'] = None

            if parent_id:
                if parent_id not in self.category_hierarchy:
                    self.category_hierarchy[parent_id] = []
                self.category_hierarchy[parent_id].append(category_id)
        else:
            # Top-level category
            if category_id not in self.category_hierarchy:
                self.category_hierarchy[category_id] = []

        return True

    def update_category(self, category_id, **kwargs):
        """
        Update an existing category.

        Args:
            category_id (str): ID of the category to update
            **kwargs: Category properties to update

        Returns:
            bool: True if category was updated successfully, False otherwise
        """
        if category_id not in self.categories:
            return False

        # Update provided properties
        for key, value in kwargs.items():
            if key in ['name', 'description', 'icon', 'active']:
                self.categories[category_id][key] = value
            elif key == 'parent_id':
                old_parent = self.categories[category_id].get('parent_id')

                # Remove from old parent's children
                if old_parent and old_parent in self.category_hierarchy:
                    if category_id in self.category_hierarchy[old_parent]:
                        self.category_hierarchy[old_parent].remove(category_id)

                # Add to new parent's children
                if value:
                    if value not in self.category_hierarchy:
                        self.category_hierarchy[value] = []
                    self.category_hierarchy[value].append(category_id)

                # Update parent_id
                self.categories[category_id]['parent_id'] = value

        return True

    def delete_category(self, category_id):
        """
        Delete a category.

        Args:
            category_id (str): ID of the category to delete

        Returns:
            bool: True if category was deleted successfully, False otherwise
        """
        if category_id not in self.categories or category_id == self.default_category:
            return False

        # Get parent ID
        parent_id = self.categories[category_id].get('parent_id')

        # Remove from parent's children
        if parent_id and parent_id in self.category_hierarchy:
            if category_id in self.category_hierarchy[parent_id]:
                self.category_hierarchy[parent_id].remove(category_id)

        # Move children to parent or default
        if category_id in self.category_hierarchy:
            for child_id in self.category_hierarchy[category_id]:
                if parent_id:
                    # Move to grandparent
                    self.categories[child_id]['parent_id'] = parent_id
                    if parent_id not in self.category_hierarchy:
                        self.category_hierarchy[parent_id] = []
                    self.category_hierarchy[parent_id].append(child_id)
                else:
                    # Move to top level
                    self.categories[child_id]['parent_id'] = None

            # Remove from hierarchy
            del self.category_hierarchy[category_id]

        # Delete the category
        del self.categories[category_id]

        return True

    def get_category(self, category_id):
        """
        Get a category by ID.

        Args:
            category_id (str): ID of the category

        Returns:
            dict: Category information or None if not found
        """
        return self.categories.get(category_id)

    def get_all_categories(self):
        """
        Get all categories.

        Returns:
            dict: Dictionary of all categories
        """
        return self.categories

    def get_subcategories(self, parent_id):
        """
        Get all subcategories of a parent category.

        Args:
            parent_id (str): ID of the parent category

        Returns:
            list: List of subcategory IDs
        """
        return self.category_hierarchy.get(parent_id, [])

    def get_category_tree(self):
        """
        Get the complete category hierarchy tree.

        Returns:
            dict: Hierarchical structure of categories
        """
        return self.category_hierarchy

    def increment_question_count(self, category_id):
        """
        Increment the question count for a category.

        Args:
            category_id (str): ID of the category

        Returns:
            bool: True if count was incremented successfully, False otherwise
        """
        if category_id not in self.categories:
            return False

        self.categories[category_id]['question_count'] += 1
        return True

    def get_top_level_categories(self):
        """
        Get all top-level categories (no parent).

        Returns:
            list: List of top-level category IDs
        """
        return [cat_id for cat_id, cat in self.categories.items() if not cat.get('parent_id')]
