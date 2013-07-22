var app = angular.module('reviewApp',['ui.slider']);

app.controller("StatementCtrl", function ($scope, $http) {
    $scope.initdata = function() {
        $http.get('/statements?December=50ba54').success(function(response){
            $scope.extracted = response['ALL']['extracted'];
            $scope.inferred = response['ALL']['inferred'];
            angular.forEach($scope.extracted, function(value, key){
                value.correct = true;
            });
        });
    }

    /* Toggle the correctness of a topic */
    $scope.toggleCorrect = function(value){
        value.correct = !value.correct;
    }

    /* Return only correct statements */
    $scope.filterCorrect = function(statements){
        var out_statements = {};
        angular.forEach(statements, function(value, key) {
            if (value.correct) {
                out_statements[key] = value;
            }
        });
        return out_statements;
    }

    $scope.toConsole = function(){
        console.log($scope.extracted);
        $http.post('/reviewed.json', $scope.extracted).success(function(response){
            console.log("POSTed something")
        });
    }

    $scope.todos = [
        {text:'Learn AngularJS', done:false},
        {text:'Build an app', done:false}
    ];

    $scope.getTotalTodos = function () {
        return $scope.todos.length;
    };

    $scope.clearCompleted = function () {
        $scope.todos = _.filter($scope.todos, function(todo){
            return !todo.done;
        });
    };

    $scope.addTodo = function () {
        $scope.todos.push({text:$scope.formTodoText, done:false});
        $scope.formTodoText = '';
    };
})
